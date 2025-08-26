import os, io, re, base64
from pathlib import Path  # <- Si no lo usas más abajo, puedes borrarlo luego.
import datetime           # <- Si no lo usas más abajo, puedes borrarlo luego.

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image

import streamlit as st
import mysql.connector
from mysql.connector import Error
import streamlit.components.v1 as components

# ===== DB Bootstrap & Helpers (auto-added) =====

# === Favicon limpio a partir del logo (cuadra y centra con transparencia) ===
def _make_square_icon(path, size=256, bg=(0, 0, 0, 0)):
    try:
        im = Image.open(path).convert("RGBA")
        w, h = im.size
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), bg)
        canvas.paste(im, ((side - w) // 2, (side - h) // 2), im)
        return canvas.resize((size, size), resample=Image.LANCZOS)
    except Exception:
        return None

icon_img = _make_square_icon("logo_epm.png", size=256)

st.set_page_config(
    page_title="Floccam Analyzer",
    page_icon=(icon_img or "🧪"),  # fallback en caso de que no cargue el PNG
    layout="wide",
    initial_sidebar_state="expanded",
)

# Personaliza el botón que colapsa la barra lateral
components.html(
    """
    <script>
    const toggle = window.parent.document.querySelector('button[data-testid="collapsedControl"]');
    if (toggle) {
      toggle.classList.add('side-toggle');
      toggle.textContent = '📊';
      toggle.title = 'Mostrar/ocultar barra lateral';
    }
    </script>
    """,
    height=0,
    width=0,
)

def jump_to_tab(tab_label: str):
    """Hace click en la pestaña cuyo texto (label) coincida exactamente."""
    components.html(f"""
    <script>
    const label = `{tab_label}`.trim();
    // Espera breve para asegurar que las tabs estén en el DOM
    setTimeout(() => {{
      const tabs = window.parent.document.querySelectorAll('[data-baseweb="tab"]');
      for (const t of tabs) {{
        const text = (t.innerText || t.textContent || '').trim();
        if (text === label) {{
          t.click();
          break;
        }}
      }}
    }}, 80);
    </script>
    """, height=0, width=0)

# === Cargar estilos EPM desde archivo CSS ===
def local_css(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"No pude cargar {path}: {e}")

# Carga el CSS (el archivo está en la misma carpeta que app_final2.py)
local_css("style_epm.css")


def get_db_connection(mysql_password=None):
    """
    Devuelve una conexión mysql.connector.connect.
    - Si st.secrets['mysql'] existe (Streamlit Cloud / .streamlit/secrets.toml), lo usa.
    - Si no, hace fallback a localhost usando mysql_password (uso local).
    """
    try:
        cfg = st.secrets["mysql"]
        host = cfg.get("host"); user = cfg.get("user")
        password = cfg.get("password"); database = cfg.get("database")
        port = int(cfg.get("port")) if cfg.get("port") else 3306
        return mysql.connector.connect(
            host=host, user=user, password=password, database=database, port=port
        )
    except Exception:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password=mysql_password or "Emanuel10*",
            database="mediciones_db",
            port=3306,
        )

def bootstrap_graficos_table():
    ddl = """
    CREATE TABLE IF NOT EXISTS graficos (
      id INT AUTO_INCREMENT PRIMARY KEY,
      planta VARCHAR(100) NOT NULL,
      fecha DATE NOT NULL,
      nombre_medicion VARCHAR(255) NOT NULL,
      tipo VARCHAR(80) DEFAULT NULL,
      nombre_archivo VARCHAR(255) NOT NULL,
      formato VARCHAR(10) DEFAULT 'PNG',
      imagen_blob LONGBLOB NOT NULL,
      ancho INT DEFAULT NULL,
      alto INT DEFAULT NULL,
      creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        mysql_pwd = st.session_state.get("mysql_password", None)
        conn = get_db_connection(mysql_pwd)
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(ddl)
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        st.warning(f"No pude crear/verificar la tabla graficos: {e}")


def bootstrap_graficos_indexes():
    """Crea índices útiles si no existen (idempotente)."""
    try:
        mysql_pwd = st.session_state.get("mysql_password", None)
        conn = get_db_connection(mysql_pwd)
        if not conn:
            return
        cur = conn.cursor()

        def _ensure_index(index_name: str, cols: str):
            cur.execute(
                """
                SELECT COUNT(1)
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = 'graficos'
                  AND index_name = %s
                """, (index_name,))
            exists = cur.fetchone()[0] > 0
            if not exists:
                cur.execute(f"CREATE INDEX {index_name} ON graficos ({cols})")

        _ensure_index("idx_graficos_pftm", "planta, fecha, tipo, nombre_medicion")
        _ensure_index("idx_graficos_pfta", "planta, fecha, tipo, nombre_archivo")

        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        st.warning(f"No pude crear/verificar índices en 'graficos': {e}")

def bootstrap_historico_indexes():
    """Crea índices para acelerar consultas en la pestaña Históricos."""
    try:
        mysql_pwd = st.session_state.get("mysql_password", None)
        conn = get_db_connection(mysql_pwd)
        if not conn:
            return
        cur = conn.cursor()

        def _ensure_index(index_name: str, cols: str):
            cur.execute(
                """
                SELECT COUNT(1)
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = 'historico'
                  AND index_name = %s
                """,
                (index_name,),
            )
            exists = cur.fetchone()[0] > 0
            if not exists:
                cur.execute(f"CREATE INDEX {index_name} ON historico ({cols})")

        # Para SELECT DISTINCT planta / fecha y filtros por planta+fecha
        _ensure_index("idx_hist_pf", "planta, fecha")
        # Para filtros + agrupaciones por nombre_medicion en esa misma combinación
        _ensure_index("idx_hist_pf_nom", "planta, fecha, nombre_medicion")

        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        st.warning(f"No pude crear/verificar índices en 'historico': {e}")


def cargar_graficos_db(planta, fecha, tipo=None, nombre_medicion=None, mysql_password=None):
    """Lectura de imágenes desde BD, tolerante para TVD por patrón de filename."""
    
    # Resolver password de forma explícita y SIEMPRE usar get_db_connection
    mysql_pwd = mysql_password if mysql_password is not None else st.session_state.get("mysql_password", None)
    conn = get_db_connection(mysql_pwd)
    if not conn:
        return []
    cur = conn.cursor()

    def _safe(s: str) -> str:
        return re.sub(r"\W+", "_", (s or "").lower()).strip("_")

    # Caso especial: TVD con nombre, tolerante al tipo
    if tipo == 'tiempo_vs_diametro' and nombre_medicion is not None:
        base = (nombre_medicion or "").lower()
        nombre_safe = _safe(base)
        q = """
            SELECT nombre_archivo, formato, imagen_blob, nombre_medicion, tipo
            FROM graficos
            WHERE planta = %s AND fecha = %s
              AND (
                    (tipo = 'tiempo_vs_diametro' AND (
                         nombre_medicion = %s
                      OR LOWER(nombre_medicion) = %s
                      OR nombre_archivo LIKE %s
                    ))
                 OR (nombre_archivo LIKE %s AND nombre_archivo NOT LIKE 'grafico_%%')
              )
            ORDER BY id
        """
        params = [planta, fecha, nombre_medicion, base, f"{nombre_safe}_grafico_%", f"{nombre_safe}_grafico_%"]
        cur.execute(q, tuple(params))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows

    # Resto de casos
    q = """
        SELECT nombre_archivo, formato, imagen_blob, nombre_medicion, tipo
        FROM graficos
        WHERE planta = %s AND fecha = %s
    """
    params = [planta, fecha]
    if tipo:
        q += " AND tipo = %s"
        params.append(tipo)
    if nombre_medicion is not None:
        base = (nombre_medicion or "").lower()
        nombre_safe = _safe(base)
        q += """
            AND (
                 nombre_medicion = %s
              OR LOWER(nombre_medicion) = %s
              OR nombre_archivo LIKE %s
            )
        """
        params += [nombre_medicion, base, f"{nombre_safe}_grafico_%"]
    q += " ORDER BY id"
    cur.execute(q, tuple(params))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def precompute_otros_desde_db(mysql_password=None):
    """Genera 'Otros' (largestfloc, mass_fraction, clarity, fractal_dimension) en modo headless."""
    try:
        mysql_pwd = mysql_password if mysql_password is not None else st.session_state.get("mysql_password", None)
        conn = get_db_connection(mysql_pwd)
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("SELECT * FROM mediciones")
        df_total = pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])
        cur.close(); conn.close()
    except Exception as e:
        st.warning(f"No pude leer 'mediciones' para precalcular 'Otros': {e}")
        return
    if df_total.empty:
        return

    variables = ["largestfloc", "mass_fraction", "clarity", "fractal_dimension"]
    for medicion_sel, grupo in df_total.groupby("nombre_medicion"):
        grupo = grupo.sort_values("unix_time").copy()
        if "unix_time" not in grupo.columns:
            continue
        grupo["tiempo"] = grupo["unix_time"] - grupo["unix_time"].min()
        for variable_sel in variables:
            if variable_sel not in grupo.columns:
                continue
            y = grupo[variable_sel].to_numpy()
            t = grupo["tiempo"].to_numpy()
            if y.size == 0:
                continue
            fig, ax = plt.subplots()
            ax.plot(t, y, marker="o", label=variable_sel)
            ax.legend()
            try:
                fig = estilizar_grafico(fig, ax, f"{variable_sel} en el tiempo - {medicion_sel}", ylabel=variable_sel)
            except Exception:
                pass
            nombre_archivo = f"otros_{medicion_sel}_{variable_sel}.png"
            store_fig_in_memory(fig, nombre_archivo)
            plt.close(fig)

# --- Bootstrap de BD (una vez por sesión) ---
if "schema_ready" not in st.session_state:
    try:
        bootstrap_graficos_table()
        bootstrap_graficos_indexes()
        bootstrap_historico_indexes()
        st.session_state["schema_ready"] = True
    except Exception as _e:
        st.warning(f"Bootstrap de BD falló: {_e}")



# ------------------- INICIO: helpers para guardado temporal -------------------
if "graficos_temp" not in st.session_state:
    st.session_state["graficos_temp"] = {}
if "csvs_temp" not in st.session_state:
    st.session_state["csvs_temp"] = {}
if "df_resumen_db" not in st.session_state:
    st.session_state["df_resumen_db"] = None

def store_fig_in_memory(fig, filename):
    """Guarda una figura matplotlib en memoria (bytes) en st.session_state['graficos_temp']"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    st.session_state["graficos_temp"][filename] = buf.getvalue()

def store_csv_in_memory(df, filename):
    """Guarda un CSV (como texto) en memoria en st.session_state['csvs_temp']"""
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.session_state["csvs_temp"][filename] = buf.getvalue()

def persist_saved_project(output_folder, fecha_analisis, planta, mysql_password):
    """
    Persiste los archivos almacenados en memoria a disco y guarda el histórico en la BD.
    También elimina las mediciones relacionadas de la tabla `mediciones` y borra archivos
    temporales `resumen_mediciones_*.csv` del folder si existieran.
    """
    os.makedirs(output_folder, exist_ok=True)

    # 1) Escribir imágenes a disco (opcional)
    for fname, b in st.session_state.get("graficos_temp", {}).items():
        with open(os.path.join(output_folder, fname), "wb") as f:
            f.write(b)

    # 2) Guardar imágenes en BD (tabla graficos) UNA SOLA VEZ
    try:
        conn_g = get_db_connection(mysql_password)
        cur_g = conn_g.cursor()

        for fname, b in st.session_state.get("graficos_temp", {}).items():
            # Derivar tipo / nombre_medicion desde el nombre del archivo
            # Convenciones actuales:
            #   "{nombre_safe}_grafico_..." -> tipo='tiempo_vs_diametro'
            #   "grafico_..."               -> tipo='comparativo'
            #   "otros_{medicion}_{var}.png"-> tipo='otros'
            tipo = 'otros'
            nombre_medicion = ''

            if fname.startswith('otros_'):
                base_noext = fname[:-4] if fname.lower().endswith('.png') else fname
                resto = base_noext.split('otros_', 1)[-1]
                parts = resto.split('_')
                if len(parts) > 1:
                    nombre_medicion = '_'.join(parts[:-1])

            if '_grafico_' in fname and not fname.startswith('grafico_'):
                tipo = 'tiempo_vs_diametro'
                nombre_medicion = fname.split('_grafico_')[0]
            elif fname.startswith('grafico_'):
                tipo = 'comparativo'
                # nombre_medicion se queda ''

            cur_g.execute(
                """
                INSERT INTO graficos(planta, fecha, nombre_medicion, tipo, nombre_archivo, formato, imagen_blob)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (planta, fecha_analisis, nombre_medicion, tipo, fname, 'PNG', b)
            )

        conn_g.commit()
        cur_g.close(); conn_g.close()
    except Exception as e:
        st.warning(f"No pude insertar imágenes en 'graficos': {e}")

    # 3) Insertar en historico (si existe df_resumen_db en sesión)
    df_db = st.session_state.get("df_resumen_db")
    if df_db is not None and not df_db.empty:
        mysql_password_hist = st.session_state.get("mysql_password", None)
        conn = get_db_connection(mysql_password_hist)
        cursor = conn.cursor()
        for _, fila in df_db.iterrows():
            cursor.execute("""
                INSERT INTO historico (nombre_medicion, fecha, planta, di, df, delta_d, dt, t63)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                fila["nombre_medicion"],
                fecha_analisis,
                planta,
                fila["di"],
                fila["df"],
                fila["delta_d"],
                fila["dt"],
                fila["t63"]
            ))
        conn.commit()

        # 4) Eliminar mediciones de la tabla `mediciones` para esos nombres (limpieza)
        nombres = tuple(df_db["nombre_medicion"].unique().tolist())
        if len(nombres) == 1:
            cursor.execute("DELETE FROM mediciones WHERE nombre_medicion = %s", (nombres[0],))
        elif len(nombres) > 1:
            placeholders = ",".join(["%s"] * len(nombres))
            cursor.execute(f"DELETE FROM mediciones WHERE nombre_medicion IN ({placeholders})", nombres)
        conn.commit()

        cursor.close()
        conn.close()

    # 5) Limpiar temporales de sesión
    st.session_state.pop("graficos_temp", None)
    st.session_state.pop("csvs_temp", None)
    st.session_state.pop("df_resumen_db", None)

    st.success("✅ Proyecto guardado en disco y en la tabla `historico`.")


# --- Logo EPM: loader robusto (busca en varias rutas y no rompe si falta) ---
def load_logo_b64():
    posibles = [
        "logo_epm.png",
        "assets/logo_epm.png",
        "static/logo_epm.png",
    ]
    for p in posibles:
        if os.path.exists(p):
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return None  # si no lo encuentra, seguimos sin romper la UI

logo_b64 = load_logo_b64()


# Tarjetas de KPI (usan variables del tema, con fallback por si no cargara el CSS)
def tarjeta_kpi(titulo, valor, unidad=""):
    st.markdown(
        f"""
        <div style="
            background-color: var(--epm-green-100, #f2fdf5);
            border: 2px solid var(--epm-green, #009739);
            border-radius: 10px;
            padding: 15px;
            text-align: center;
            margin-bottom: 10px;
        ">
            <h4 style="color: var(--epm-green, #009739); margin: 0;">{titulo}</h4>
            <p style="font-size: 1.5em; font-weight: bold; margin: 5px 0;">
                {valor} {unidad}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Badges de estado (verde por defecto, acepta override con 'color')
def badge_estado(texto, color="var(--epm-green, #009739)"):
    st.markdown(
        f"""
        <span style="
            background-color: {color};
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.85em;
            display: inline-block;
        ">
            {texto}
        </span>
        """,
        unsafe_allow_html=True,
    )


# Estilo institucional para gráficos con título y ejes personalizados
def estilizar_grafico(fig, ax, titulo, xlabel="Tiempo (s)", ylabel=None):
    ax.set_title(titulo, fontsize=14, fontweight="bold", color="#009739")
    ax.set_xlabel(xlabel, fontsize=12)

    if ylabel:
        ax.set_ylabel(ylabel, fontsize=12)
    else:
        ax.set_ylabel(ax.get_ylabel(), fontsize=12)

    ax.tick_params(axis='both', labelsize=10)
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.3)
    ax.legend(loc="best", fontsize=10)
    fig.patch.set_facecolor("#f9fdfb")
    ax.set_facecolor("#ffffff")
    fig.tight_layout()
    return fig

# --- Encabezado: logo + título (estilos en style_epm.css) ---
st.markdown(f"""
<div class="app-topbar">
  {f'<img src="data:image/png;base64,{logo_b64}" alt="EPM" />' if logo_b64 else ''}
  <div class="app-title-wrap">
    <h1 class="app-title">Floccam Analyzer</h1>
  </div>
</div>
""", unsafe_allow_html=True)

# Carpeta para gráficos
output_folder = "graficos_mediciones"
os.makedirs(output_folder, exist_ok=True)

# Variables de sesión
if "procesado" not in st.session_state:
    st.session_state["procesado"] = False

# Columnas esperadas
columnas_medicion_temp = [
    'ascii_time', 'excel_time', 'unix_time', 'diameter', 'number',
    'mass_fraction', 'skew1', 'skew2', 'skew3', 'fractal_dimension',
    'sphericity', 'clarity', 'brightness', 'sizea', 'sizev',
    'size01', 'size02', 'size03', 'dividersize',
    'aveaspectv', 'avewidthv', 'avelengthv', 'largestfloc'
]
columnas_mediciones = [
    'nombre_medicion', 'unix_time', 'diameter', 'number',
    'mass_fraction', 'skew1', 'skew2', 'skew3', 'fractal_dimension',
    'sphericity', 'clarity', 'largestfloc'
]

# --- Barra lateral: Estado del sistema + Acciones rápidas + Consejos ---
with st.sidebar:
    st.markdown("### Estado del sistema")

    # Pill helper simple (colores EPM-ish)
    def _pill(text, bg="#E3F6ED", fg="#0F7B3B"):
        st.markdown(
            f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:12px; font-size:0.85em; display:inline-block;'>{text}</span>",
            unsafe_allow_html=True,
        )

    # 🔌 Salud de la BD (prueba rápida)
    ok_db = False
    try:
        _pwd = st.session_state.get("mysql_password", None)
        _conn = get_db_connection(_pwd)
        if _conn:
            _cur = _conn.cursor()
            _cur.execute("SELECT 1")
            _cur.fetchone()
            ok_db = True
            _cur.close(); _conn.close()
    except Exception:
        ok_db = False

    if ok_db:
        _pill("BD conectada")
    else:
        _pill("BD desconectada", bg="#FDECEC", fg="#B3261E")

    # Resumen rápido de sesión
    st.write(f"🖼️ Gráficos en memoria: **{len(st.session_state.get('graficos_temp', {}))}**")
    st.write(f"📄 CSVs en memoria: **{len(st.session_state.get('csvs_temp', {}))}**")

    st.markdown("---")
    st.markdown("### Acciones rápidas")
    if st.button("🧹 Limpiar temporales", use_container_width=True):
        st.session_state.pop("graficos_temp", None)
        st.session_state.pop("csvs_temp", None)
        st.session_state.pop("df_resumen_db", None)
        st.success("Temporales limpiados.")

    st.markdown("---")
    with st.expander("💡 Consejos y atajos"):
        st.markdown(
            "- Desplaza la barra de pestañas ↔ para ver más secciones.\n"
            "- En **Históricos**, puedes eliminar mediciones y sus gráficos asociados.\n"
            "- Los **gráficos** y **CSV** se guardan cuando confirmas en **Guardar información**.\n"
            "- Si el logo se viera recortado, actualiza la página (F5)."
        )


# --- Tabs principales 

tab_ingreso, tab_procesamiento, tab_comparativos, tab_graficos, tab_guardar, tab_historicos = st.tabs([
    "📝 Ingreso de información",
    "🔬 Procesamiento",
    "📈 Comparativos",
    "📊 Otros gráficos",
    "💾 Guardar información",
    "📂 Históricos"
])

if st.session_state.get("goto_tab"):
    jump_to_tab(st.session_state.pop("goto_tab"))


# Tip visible para el usuario
st.markdown(
    "<div class='tab-help' style='color:#777; margin:-6px 0 10px 2px;'>"
    "Sugerencia: desplaza la barra de pestañas ↔ para ver más secciones."
    "</div>",
    unsafe_allow_html=True
)

def extraer_dosis(nombre_medicion):
    partes = nombre_medicion.strip().split("_")
    try:
        dosis_c = float(partes[-2])
        dosis_f = float(partes[-1])
        return dosis_c, dosis_f
    except (IndexError, ValueError):
        return None, None



# 📥 INGRESO DE INFORMACIÓN
with tab_ingreso:
    #st.subheader("Ingreso de parámetros y carga de datos")
 # 🔁 Botón temporal para reiniciar estado (útil para desarrollo)
    if st.button("🧹 Resetear estado (debug)"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.experimental_rerun()

        # Contraseña (solo para uso local). En producción se utilizará st.secrets.
    mysql_password = st.text_input("🔐 Contraseña de MySQL (solo local)", type="password")
    try:
        secrets_present = "mysql" in st.secrets
    except Exception:
        secrets_present = False


    planta = st.text_input("🏭 Nombre de la planta")
    fecha_analisis = st.date_input("📅 Fecha del análisis", value=datetime.date.today())
    notas = st.text_area("📝 Comentarios del ensayo")
    archivos = st.file_uploader("📁 Subir archivo(s) CSV", type="csv", accept_multiple_files=True)
    accion = st.radio("¿Qué hacer con los datos anteriores?", ["Conservar", "Eliminar todo antes de cargar"])

    # Permitir iniciar procesamiento si se ingresó contraseña local o si hay st.secrets en producción
    if st.button("🚀 Iniciar procesamiento") and (mysql_password or secrets_present) and archivos:
        st.session_state["procesado"] = True
        # Guardar la contraseña en sesión SOLO si se ingresó (para local). En producción, st.secrets es usado.
        if mysql_password:
            st.session_state["mysql_password"] = mysql_password
        else:
            st.session_state["mysql_password"] = ""
        st.session_state["archivos"] = archivos
        st.session_state["planta"] = planta
        st.session_state["fecha_analisis"] = fecha_analisis
        st.session_state["notas"] = notas
        st.session_state["accion"] = accion
    # --- Navegación: ir a la siguiente pestaña ---
    st.markdown("<hr>", unsafe_allow_html=True)
    _, _, next_col = st.columns([6, 4, 2])
    with next_col:
        if st.button("Siguiente ▶", key="next_from_ingreso"):
            st.session_state["goto_tab"] = "🔬 Procesamiento"  # debe coincidir EXACTO con el label de la pestaña

    


# 🔍 PROCESAMIENTO
with tab_procesamiento:
    if st.session_state["procesado"]:
        mysql_password = st.session_state["mysql_password"]
        archivos = st.session_state["archivos"]
        planta = st.session_state["planta"]
        fecha_analisis = st.session_state["fecha_analisis"]
        notas = st.session_state["notas"]
        accion = st.session_state["accion"]

        conn = get_db_connection(mysql_password)
        cursor = conn.cursor()

        df_manual_dict = {}
        resumen = []

        if accion == "Eliminar todo antes de cargar":
            cursor.execute("DELETE FROM mediciones")
            conn.commit()

        for archivo in archivos:
            nombre_medicion = Path(archivo.name).stem
            try:
                df = pd.read_csv(io.StringIO(archivo.getvalue().decode("utf-8")))
                if df.empty or df.shape[1] == 0:
                    st.error(f"❌ El archivo `{archivo.name}` no contiene datos válidos.")
                    continue
            except Exception as e:
                st.error(f"❌ No se pudo leer el archivo `{archivo.name}`: {e}")
                continue

            
            df.columns = [re.sub(r'\W+', '_', col.strip().lower()) for col in df.columns]

            cursor.execute("DELETE FROM medicion_temp")
            conn.commit()

            columnas_str = ', '.join(columnas_medicion_temp)
            placeholders = ', '.join(['%s'] * len(columnas_medicion_temp))
            insert_temp_sql = f"INSERT INTO medicion_temp ({columnas_str}) VALUES ({placeholders})"
            valores = df[columnas_medicion_temp].values.tolist()
            cursor.executemany(insert_temp_sql, valores)
            conn.commit()

            insert_mediciones_sql = f"""INSERT INTO mediciones (nombre_medicion, unix_time, diameter, number,
                    mass_fraction, skew1, skew2, skew3, fractal_dimension,
                    sphericity, clarity, largestfloc)
                    SELECT %s, unix_time, diameter, number, mass_fraction, skew1, skew2, skew3,
                    fractal_dimension, sphericity, clarity, largestfloc FROM medicion_temp"""
            cursor.execute(insert_mediciones_sql, (nombre_medicion,))
            conn.commit()
            cursor.execute("DELETE FROM medicion_temp")
            conn.commit()

        cursor.execute("SELECT * FROM mediciones")
        df_total = pd.DataFrame(cursor.fetchall(), columns=[col[0] for col in cursor.description])
        for nombre, grupo in df_total.groupby("nombre_medicion"):
            grupo = grupo.sort_values("unix_time")
            grupo["tiempo"] = grupo["unix_time"] - grupo["unix_time"].min()
            tiempo = grupo["tiempo"].to_numpy()
            diam = grupo["diameter"].to_numpy()
            if len(diam) == 0:
                continue
            di = diam[0]
            fig, ax = plt.subplots()
            ax.plot(tiempo, diam, marker="o", color="#009739", linewidth=2, label=nombre)

            ax.legend()

            fig = estilizar_grafico(
                fig, ax,
                f"🔬 Tiempo vs Diámetro - {nombre}",
                ylabel="Diámetro (mm)"
            )
            st.pyplot(fig)
            # Guardar figura Tiempo vs Diámetro en memoria (para guardado final)
            fecha_str = fecha_analisis.strftime("%Y%m%d") if hasattr(fecha_analisis, "strftime") else str(fecha_analisis)
            planta_safe = re.sub(r'\W+', '_', planta)
            nombre_safe = re.sub(r'\W+', '_', nombre)
            store_fig_in_memory(fig, f"{nombre_safe}_grafico_{planta_safe}_{fecha_str}.png")

            df_input = st.number_input(f"📍 Ingresa Df para '{nombre}'", min_value=0.0, step=0.1, format="%.3f", key=nombre)
            df_manual_dict[nombre] = {"df_manual": df_input, "grupo": grupo}

        if st.button("⚙️ Procesar mediciones"):
            for nombre, datos in df_manual_dict.items():
                grupo = datos["grupo"]
                df_manual = datos["df_manual"]
                tiempo = grupo["tiempo"].to_numpy()
                diam = grupo["diameter"].to_numpy()
                di = diam[0]
                delta_d = df_manual - di
                objetivo = di + 0.63 * delta_d
                idx_t63 = np.abs(diam - objetivo).argmin()
                t_63 = tiempo[idx_t63] if len(tiempo) > idx_t63 else np.nan
                d_t = diam.max()

                resumen.append({
                    "nombre_medicion": nombre,
                    "Di (mm)": di,
                    "Df (mm)": df_manual,
                    "ΔD (mm)": delta_d,
                    "D(T) (mm)": d_t,
                    "T_63 (s)": t_63
                })

                fig2, ax2 = plt.subplots()
                ax2.plot(tiempo, diam, marker="o", color="#009739", linewidth=2, label="Diámetro")
                ax2.axhline(objetivo, color="#D85400", linestyle="--", linewidth=2, label="63% ΔD")
                ax2.axvline(t_63, color="#007a2f", linestyle="--", linewidth=2, label="T₆₃")

                fig2 = estilizar_grafico(fig2, ax2, f"🎯 Curva y puntos clave - {nombre}", ylabel="Diámetro (mm)")
                st.pyplot(fig2)
                store_fig_in_memory(fig2, f"{nombre_safe}_curva_y_puntos_{planta_safe}_{fecha_str}.png")


            df_resumen = pd.DataFrame(resumen)
            
            st.markdown("### 🧾 Resumen de mediciones procesadas")

            for fila in resumen:
                st.markdown(f"#### 📌 {fila['nombre_medicion']}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    tarjeta_kpi("Di", round(fila["Di (mm)"], 3), "mm")
                with col2:
                    tarjeta_kpi("Df", round(fila["Df (mm)"], 3), "mm")
                with col3:
                    tarjeta_kpi("T₆₃", round(fila["T_63 (s)"], 1), "s")
                st.markdown("---")


            st.markdown(
                df_resumen.style
                .set_table_attributes("style='border-collapse:collapse; width:100%'")
                .set_properties(**{
                    "text-align": "center",
                    "border": "1px solid #ddd",
                    "padding": "8px"
                })
                .hide(axis="index")
                .to_html(),
                unsafe_allow_html=True
            )

            st.session_state["df_resumen"] = df_resumen

	    # Preparar versión para la base de datos (renombrar columnas)
            df_resumen_db = df_resumen.rename(columns={
                "Di (mm)": "di",
                "Df (mm)": "df",
                "ΔD (mm)": "delta_d",
                "D(T) (mm)": "dt",
                "T_63 (s)": "t63"
            })
            st.session_state["df_resumen_db"] = df_resumen_db

            # Guardar CSV en memoria
            fecha_str = fecha_analisis.strftime("%Y%m%d") if hasattr(fecha_analisis, "strftime") else str(fecha_analisis)
            csv_name = f"resumen_mediciones_{fecha_str}_{planta}.csv"
            store_csv_in_memory(df_resumen_db, csv_name)

            st.info("📁 Resumen guardado temporalmente en memoria. Usa la pestaña '💾 Guardar información' para persistir el proyecto.")



            cursor.close()
            conn.close()

# 📈 COMPARATIVOS
with tab_comparativos:
    st.subheader("📈 Gráficos comparativos de dosis vs T₆₃")

    if "df_resumen" in st.session_state:
        df_resumen = st.session_state["df_resumen"]
       

        # Asegurarse de que las columnas de dosis estén presentes
        def extraer_dosis(nombre):
            partes = nombre.strip().split("_")
            try:
                coagulante = float(partes[-2])
                floculante = float(partes[-1])
                return coagulante, floculante
            except (IndexError, ValueError):
                return None, None

        df_resumen[['dosis_coagulante', 'dosis_floculante']] = df_resumen['nombre_medicion'].apply(
            lambda x: pd.Series(extraer_dosis(x))
        )

        df_resumen = df_resumen.dropna(subset=['dosis_coagulante', 'dosis_floculante', 'T_63 (s)'])

        output_folder = "graficos_mediciones"
        os.makedirs(output_folder, exist_ok=True)

        # Gráfico 1: coagulante vs T63 (varias curvas según dosis de floculante)
        fig1, ax1 = plt.subplots()
        dosis_floculantes = sorted(df_resumen['dosis_floculante'].unique())

        for dosis_flo in dosis_floculantes:
            subgrupo = df_resumen[df_resumen['dosis_floculante'] == dosis_flo]
            if not subgrupo.empty:
                ax1.plot(subgrupo['dosis_coagulante'], subgrupo['T_63 (s)'], 'o-', label=f"Floculante = {dosis_flo}")

        fig1 = estilizar_grafico(
            fig1, ax1,
            "Dosis coagulante vs T₆₃ (según dosis de floculante)",
            ylabel="T₆₃ (s)"
        )
        st.pyplot(fig1)

        # Guardar con planta y fecha
        fecha_str = st.session_state["fecha_analisis"].strftime("%Y%m%d")
        planta_actual = st.session_state.get("planta", "planta")
        store_fig_in_memory(fig1, f"grafico_coagulante_vs_t63_{planta_actual}_{fecha_str}.png")


        # Gráfico 2: dosis floculante vs T63 (coagulante fijo)
        coag_fijos = df_resumen['dosis_coagulante'].unique()
        for dc in coag_fijos:
            grupo2 = df_resumen[df_resumen['dosis_coagulante'] == dc]
            if len(grupo2['dosis_floculante'].unique()) > 1:
                fig2, ax2 = plt.subplots()
                ax2.plot(grupo2['dosis_floculante'], grupo2['T_63 (s)'], 'o-', label=f"Coagulante: {dc}")
                fig2 = estilizar_grafico(
                    fig2, ax2,
                    f"Dosis floculante vs T₆₃ (coagulante fijo = {dc})",
                    ylabel="T₆₃ (s)"
                )
                st.pyplot(fig2)
                store_fig_in_memory(fig2, f"grafico_floculante_vs_t63_dc_{dc}.png")

        # Gráfico 3: comparación floculante por planta
        planta_actual = st.session_state.get("planta", "")
        grupo3 = df_resumen[df_resumen['nombre_medicion'].str.contains(planta_actual)]
        if not grupo3.empty:
            dosis_flo_uniques = grupo3['dosis_floculante'].unique()
            if len(dosis_flo_uniques) > 1:
                fig3, ax3 = plt.subplots()
                for dflo in dosis_flo_uniques:
                    subgrupo = grupo3[grupo3['dosis_floculante'] == dflo]
                    ax3.plot(subgrupo['dosis_coagulante'], subgrupo['T_63 (s)'], 'o-', label=f"Floculante: {dflo}")
                fig3 = estilizar_grafico(
                    fig3, ax3,
                    f"Comparación de floculante - Planta: {planta_actual}",
                    ylabel="T₆₃ (s)"
                )
                st.pyplot(fig3)
                store_fig_in_memory(fig3, f"grafico_comparacion_floculante_{planta_actual}.png")

        # 📉 NUEVO: Gráfico delta D vs coagulante, agrupado por dosis de floculante
        fig4, ax4 = plt.subplots()
        for dosis_flo in sorted(df_resumen['dosis_floculante'].unique()):
            subgrupo = df_resumen[df_resumen['dosis_floculante'] == dosis_flo]
            if not subgrupo.empty:
                ax4.plot(subgrupo['dosis_coagulante'], subgrupo['ΔD (mm)'], 'o-', label=f"Floculante = {dosis_flo}")
        fig4 = estilizar_grafico(
            fig4, ax4,
            "Dosis coagulante vs ΔD (por dosis de floculante)",
            ylabel="ΔD (mm)"
        )
        st.pyplot(fig4)
        store_fig_in_memory(fig4, f"grafico_coagulante_vs_deltaD_{planta_actual}_{fecha_str}.png")


        # 📉 NUEVO: Gráfico delta D vs floculante, agrupado por dosis de coagulante
        for dc in sorted(df_resumen['dosis_coagulante'].unique()):
            grupo_dc = df_resumen[df_resumen['dosis_coagulante'] == dc]
            if len(grupo_dc['dosis_floculante'].unique()) > 1:
                fig5, ax5 = plt.subplots()
                ax5.plot(grupo_dc['dosis_floculante'], grupo_dc['ΔD (mm)'], 'o-', label=f"Coagulante = {dc}")
                fig5 = estilizar_grafico(
                    fig5, ax5,
                    f"Dosis floculante vs ΔD (coagulante fijo = {dc})",
                    ylabel="ΔD (mm)"
                )
                st.pyplot(fig5)
                store_fig_in_memory(fig5, f"grafico_floculante_vs_deltaD_dc_{dc}_{planta_actual}_{fecha_str}.png")



    else:
        st.warning("⚠️ Aún no se ha procesado ninguna medición. Procesa datos en la pestaña 'Procesamiento'.")


# 📉 OTROS GRÁFICOS
with tab_graficos:
    st.subheader("📉 Visualización por variable")

    # Verificar si hay secrets (producción)
    try:
        secrets_present = "mysql" in st.secrets
    except Exception:
        secrets_present = False

    if secrets_present:
        conn = mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            port=st.secrets["mysql"]["port"]
        )
    else:
        mysql_password = st.session_state.get("mysql_password", "")
        if mysql_password:
            conn = mysql.connector.connect(
                host="localhost",
                user="root",
                password=mysql_password,
                database="mediciones_db",
                port=3306
            )
        else:
            st.warning("🔑 Ingresa tu contraseña en la pestaña 'Ingreso de información' para acceder a esta sección.")
            conn = None

    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM mediciones")
        df_total = pd.DataFrame(cursor.fetchall(), columns=[col[0] for col in cursor.description])

        mediciones = df_total["nombre_medicion"].unique().tolist()
        medicion_sel = st.selectbox("Medición", mediciones)
        variable_sel = st.selectbox("Variable", ["largestfloc", "mass_fraction", "clarity", "fractal_dimension"])

        grupo = df_total[df_total["nombre_medicion"] == medicion_sel].sort_values("unix_time")
        grupo["tiempo"] = grupo["unix_time"] - grupo["unix_time"].min()
        y = grupo[variable_sel].to_numpy()
        tiempo = grupo["tiempo"].to_numpy()

        valor_maximo = np.round(y.max(), 4)

        # 🟢 Título con nombre de la medición
        st.markdown(f"#### 📌 Medición seleccionada: `{medicion_sel}`")

        # 🔢 KPI
        col1, col2 = st.columns(2)
        with col1:
            tarjeta_kpi("Variable", variable_sel)
        with col2:
            tarjeta_kpi("Valor máx.", valor_maximo)

        # 📈 Gráfico estilizado
        fig, ax = plt.subplots()
        ax.plot(tiempo, y, marker="o", color="#009739", label=variable_sel)
        ax.legend()

        fig = estilizar_grafico(
            fig, ax,
            f"{variable_sel} en el tiempo - {medicion_sel}",
            ylabel=variable_sel
        )
        st.pyplot(fig)

        # Guardado del gráfico
        nombre_archivo = f"otros_{medicion_sel}_{variable_sel}.png"
        store_fig_in_memory(fig, nombre_archivo)

        cursor.close()
        conn.close()

# 💾 GUARDAR INFORMACIÓN
with tab_guardar:
    st.subheader("💾 Guardar análisis actual")

    if "df_resumen" in st.session_state:
        desea_guardar = st.radio("¿Deseas guardar el análisis actual?", ["Sí", "No"], horizontal=True)

        if desea_guardar == "Sí":
            st.markdown("### 📦 Selecciona qué deseas guardar:")

            col1, col2 = st.columns(2)
            with col1:
                guardar_tabla = st.checkbox("📄 Tabla resumen", value=True)
                guardar_tiempo = st.checkbox("🕒 Gráficos: Tiempo vs Diámetro", value=True)
            with col2:
                guardar_comparativos = st.checkbox("📈 Gráficos: Comparativos")
                guardar_otros = st.checkbox("📊 Gráficos: Otros")

            st.markdown(" ")

            if st.button("✅ Confirmar guardado"):
                st.session_state["guardar_tabla"] = guardar_tabla
                st.session_state["guardar_tiempo"] = guardar_tiempo
                st.session_state["guardar_comparativos"] = guardar_comparativos
                st.session_state["guardar_otros"] = guardar_otros
                st.session_state["confirmado_guardado"] = True
                st.success("✔️ Preferencias de guardado registradas correctamente.")

            # Mostrar botón de guardado definitivo si ya se confirmaron las preferencias
            if st.session_state.get("confirmado_guardado", False):
                if st.button("💾 Guardar proyecto ahora"):
                    planta = st.session_state.get("planta", "")
                    fecha_analisis = st.session_state.get("fecha_analisis", "")
                    mysql_pwd = st.session_state.get("mysql_password", None)

                    # Conexión flexible
                    conn = get_db_connection(mysql_pwd)
                    if not conn:
                        st.error("No se pudo establecer la conexión. Ingresa la contraseña local o configura `st.secrets` en producción.")
                        st.stop()

                    # ¿Ya existe histórico de esa planta y fecha?
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT COUNT(*) FROM historico
                        WHERE planta = %s AND fecha = %s
                    """, (planta, fecha_analisis))
                    existe = cursor.fetchone()[0] > 0
                    cursor.close(); conn.close()

                    if existe:
                        opcion = st.radio(
                            "⚠️ Ya existe un guardado para esta planta y fecha. ¿Qué deseas hacer?",
                            ("Sobrescribir el anterior", "Guardar como nueva copia")
                        )

                        if opcion == "Sobrescribir el anterior":
                            # Limpieza de registros previos
                            conn = get_db_connection(mysql_pwd)
                            cursor = conn.cursor()
                            cursor.execute("""
                                DELETE FROM historico
                                WHERE planta = %s AND fecha = %s
                            """, (planta, fecha_analisis))
                            # (opcional y recomendado) también limpiar BLOBs previos:
                            try:
                                cursor.execute("""
                                    DELETE FROM graficos
                                    WHERE planta = %s AND fecha = %s
                                """, (planta, fecha_analisis))
                            except Exception:
                                pass
                            conn.commit()
                            cursor.close(); conn.close()

                            # Eliminar archivos locales asociados (si existen)
                            try:
                                for archivo in Path(output_folder).glob(f"*{planta}_{fecha_analisis.strftime('%Y%m%d')}*.png"):
                                    archivo.unlink(missing_ok=True)
                            except Exception:
                                pass

                            # Precompute 'Otros' si corresponde
                            if st.session_state.get("guardar_otros", False):
                                precompute_otros_desde_db(mysql_pwd)

                            # Guardado definitivo
                            persist_saved_project(output_folder, fecha_analisis, planta, mysql_pwd)
                            st.success("✅ Proyecto sobrescrito correctamente.")

                        elif opcion == "Guardar como nueva copia":
                            # Renombrar los artefactos en memoria con sufijo _copiaN
                            copia_num = 1
                            nuevos = {}
                            for fname, b in list(st.session_state.get("graficos_temp", {}).items()):
                                # Busca el patrón {planta}_{YYYYMMDD} en el nombre actual y añade sufijo
                                try:
                                    fecha_str = fecha_analisis.strftime('%Y%m%d')
                                except Exception:
                                    # si no es datetime/date, no forzamos
                                    fecha_str = str(fecha_analisis)
                                nuevo_nombre = fname.replace(
                                    f"{planta}_{fecha_str}",
                                    f"{planta}_{fecha_str}_copia{copia_num}"
                                )
                                nuevos[nuevo_nombre] = b
                                copia_num += 1
                            st.session_state["graficos_temp"] = nuevos

                            if st.session_state.get("guardar_otros", False):
                                precompute_otros_desde_db(mysql_pwd)

                            persist_saved_project(output_folder, fecha_analisis, planta, mysql_pwd)
                            st.success("✅ Proyecto guardado como nueva copia.")
                    else:
                        # Guardado normal (no existía)
                        if st.session_state.get("guardar_otros", False):
                            precompute_otros_desde_db(mysql_pwd)
                        persist_saved_project(output_folder, fecha_analisis, planta, mysql_pwd)
                        st.success("✅ Proyecto guardado correctamente.")

                st.markdown("""
                    <div style="background-color:#f2fdf5; border-left: 5px solid #009739; padding: 20px; border-radius: 10px; margin-top: 15px;">
                        <h4 style="margin: 0; color: #009739;">✅ Análisis listo para guardar</h4>
                        <p style="margin: 0;">Puedes ejecutar el guardado completo desde la pestaña de <strong>Procesamiento</strong> o <strong>Comparativos</strong>.</p>
                    </div>
                """, unsafe_allow_html=True)

        else:
            st.markdown("### ⚙️ ¿Qué deseas hacer con el análisis actual?")
            accion = st.radio(" ", ["Conservarlo temporalmente", "Eliminarlo"], horizontal=True)
            if accion == "Eliminarlo" and st.button("🗑️ Confirmar eliminación"):
                st.session_state.pop("df_resumen", None)
                st.success("🚫 El análisis actual ha sido eliminado.")
    else:
        st.info("ℹ️ No hay análisis procesado actualmente.")


# 📜 HISTÓRICOS
with tab_historicos:
    st.markdown("## 🌿 Consulta de históricos")

    # 🔄 Conexión flexible (local o producción)
    mysql_password_hist = st.session_state.get("mysql_password", None)
    conn = get_db_connection(mysql_password_hist)

    if conn:
        cursor = conn.cursor()

        # 🔍 Selección de planta
        cursor.execute("SELECT DISTINCT planta FROM historico ORDER BY planta")
        plantas_disponibles = [row[0] for row in cursor.fetchall()]

        if not plantas_disponibles:
            st.info("ℹ️ Aún no hay plantas registradas en el histórico.")
            cursor.close(); conn.close()
            st.stop()

        planta_sel = st.selectbox("🏭 Selecciona la planta", plantas_disponibles, key="select_planta_hist")

        # 🔍 Selección de fecha
        cursor.execute("SELECT DISTINCT fecha FROM historico WHERE planta = %s ORDER BY fecha DESC", (planta_sel,))
        fechas_disponibles = [row[0] for row in cursor.fetchall()]

        if not fechas_disponibles:
            st.info(f"ℹ️ No hay registros para la planta '{planta_sel}'.")
            cursor.close(); conn.close()
            st.stop()

        fecha_sel = st.selectbox("📅 Selecciona la fecha", fechas_disponibles, key="select_fecha_hist")

        # 📥 Consulta de datos históricos
        cursor.execute("""
            SELECT * FROM historico
            WHERE fecha = %s AND planta = %s
        """, (fecha_sel, planta_sel))
        historico_df = pd.DataFrame(cursor.fetchall(), columns=[col[0] for col in cursor.description])

        # 🧾 KPI resumen
        st.markdown("### 📊 Resumen general")
        tarjeta_kpi("Mediciones guardadas", len(historico_df))

        # 📄 Tabla resumen dentro de expander
        with st.expander("🧾 Ver tabla de mediciones guardadas"):
            st.markdown(
                historico_df.style
                .set_table_attributes("style='border-collapse:collapse; width:100%'")
                .set_properties(**{
                    "text-align": "center",
                    "border": "1px solid #ddd",
                    "padding": "8px"
                })
                .hide(axis="index")
                .to_html(),
                unsafe_allow_html=True
            )

        # 🗑️ Eliminación de mediciones
        with st.expander("🗑️ Eliminar mediciones"):
            st.markdown("### Selecciona las mediciones que deseas eliminar:")
            seleccionados = []
            for nombre in historico_df["nombre_medicion"].unique():
                if st.checkbox(f"Eliminar: {nombre}"):
                    seleccionados.append(nombre)

            if seleccionados and st.button("❌ Eliminar seleccionados"):
                for nombre in seleccionados:
                    # Borra solo en el contexto actual (planta + fecha)
                    cursor.execute(
                        "DELETE FROM historico WHERE nombre_medicion = %s AND planta = %s AND fecha = %s",
                        (nombre, planta_sel, fecha_sel)
                    )
                    conn.commit()

                    # Borrar archivos relacionados
                    nombre_safe = re.sub(r'\W+', '_', nombre)
                    planta_safe = re.sub(r'\W+', '_', planta_sel)
                    fecha_str = fecha_sel.strftime("%Y%m%d")

                    patrones = [
                        f"{nombre_safe}_grafico_{planta_safe}_{fecha_str}.png",
                        f"otros_{nombre_safe}_*.png",
                    ]
                    for patron in patrones:
                        for archivo in Path(output_folder).glob(patron):
                            archivo.unlink(missing_ok=True)

                st.success("✅ Mediciones eliminadas del histórico y gráficos correspondientes removidos.")
                st.experimental_rerun()

        # 📊 Visualización de gráficos

        

        with st.expander("🖼️ Ver gráficos guardados"):
            st.markdown("Selecciona los tipos de gráficos que deseas visualizar:")
            # Leemos desde la BD (tabla graficos)
            mysql_password_hist = st.session_state.get("mysql_password", None)

            st.markdown("Selecciona los tipos de gráficos que deseas visualizar:")
            ver_tiempo = st.checkbox("⏱️ Tiempo vs Diámetro", value=True)
            ver_comparativos = st.checkbox("📈 Comparativos")
            ver_otros = st.checkbox("📊 Otros")

            if ver_tiempo:
                st.markdown("#### ⏱️ Gráficos - Tiempo vs Diámetro")

                for nombre in historico_df["nombre_medicion"].unique():
                    rows = cargar_graficos_db(
                        planta_sel, fecha_sel,
                        tipo='tiempo_vs_diametro',
                        nombre_medicion=nombre,           # ahora filtramos en SQL
                        mysql_password=mysql_password_hist
                    )

                    if rows:
                        with st.expander(f"🧪 {nombre}"):
                            for nombre_archivo, formato, blob, _nombre_db, _tipo in rows:
                                st.image(io.BytesIO(blob), caption=nombre_archivo, use_container_width=True)
                    else:
                        st.info(f"ℹ️ No encontré imagen de '{nombre}' para {planta_sel} - {fecha_sel}.")



            if ver_comparativos:
                st.markdown("#### 📈 Gráficos comparativos")
                rows = cargar_graficos_db(
                    planta_sel, fecha_sel,
                    tipo='comparativo',
                    mysql_password=mysql_password_hist
                )
                for nombre_archivo, formato, blob, _, _ in rows:
                    with st.expander(f"📊 {nombre_archivo}"):
                        img = Image.open(io.BytesIO(blob))
                        st.image(img, caption=nombre_archivo, use_column_width=True)

            if ver_otros:
                st.markdown("#### 📊 Otros gráficos")
                rows = cargar_graficos_db(
                    planta_sel, fecha_sel,
                    tipo='otros',
                    mysql_password=mysql_password_hist
                )
                for nombre_archivo, formato, blob, nom_med, _ in rows:
                    with st.expander(f"📌 {nombre_archivo}"):
                        img = Image.open(io.BytesIO(blob))
                        st.image(img, caption=f"Otro gráfico - {nombre_archivo}", use_column_width=True)


        cursor.close()
        conn.close()
    else:
        st.error("❌ No se pudo conectar a la base de datos. Verifica la configuración de conexión.")

st.markdown("""
    <hr style="margin-top: 2em; margin-bottom: 1em;">
    <div style="text-align: center; font-size: 0.9em; color: #555;">
        © 2025 EPM | Floccam Analyzer - Todos los derechos reservados.  
        <br>
        Desarrollado para análisis de desempeño de coagulantes y floculantes.
    </div>
""", unsafe_allow_html=True)

# Cierre de conexión segura (por si algún cursor sigue activo)
try:
    if 'cursor' in locals(): cursor.close()
    if 'conn' in locals(): conn.close()
except:
    pass
