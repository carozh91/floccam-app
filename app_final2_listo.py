import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mysql.connector
import io
import os
import re
import datetime
from pathlib import Path

from PIL import Image

# Definir carpeta donde están las imágenes de las plantas
CARPETA_PLANTAS = "imagenes_plantas"

# Lista de plantas con sus archivos e identificadores
PLANTAS = [
    {"nombre": "Aguas Frías", "archivo": "aguasfrias.png"},
    {"nombre": "Barbosa", "archivo": "barbosa.png"},
    {"nombre": "Caldas", "archivo": "caldas.png"},
    {"nombre": "La Ayurá", "archivo": "laayura.png"},
    {"nombre": "La Cascada", "archivo": "lacascada.png"},
    {"nombre": "La Montaña", "archivo": "lamontaña.png"},
    {"nombre": "Manantiales", "archivo": "manantiales.png"},
    {"nombre": "Palmitas", "archivo": "palmitas.png"},
    {"nombre": "Rionegro", "archivo": "rionegro.png"},
    {"nombre": "San Antonio", "archivo": "sanantonio.png"},
    {"nombre": "San Cristóbal", "archivo": "sancristobal.png"},
    {"nombre": "San Nicolás", "archivo": "sannicolas.png"},
    {"nombre": "Villahermosa", "archivo": "villahermosa.png"}
]

def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style_epm.css")  # Asegúrate de que el archivo esté en el mismo directorio

# Configuración global
st.set_page_config(page_title="App - Procesamiento de Mediciones", layout="wide")
with st.sidebar:
    st.image("logo_epm.png", width=160)
    st.markdown("<h2 style='color:#009739; margin-top: -10px;'>Floccam Analyzer</h2>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("Bienvenido al sistema de análisis de floculación.")
    st.markdown("Selecciona una pestaña para comenzar.")

import base64

def img_to_base64(img_path):
    with open(img_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

logo_base64 = img_to_base64("logo_epm.png")

# Verificamos si ya se eligió un rol
if "rol" not in st.session_state:

    st.markdown("## 👋 Bienvenido, ¿cómo deseas ingresar a la app?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔐 Analista (requiere login)"):
            st.session_state["modo_login"] = "analista"
    with col2:
        if st.button("🔍 Consultar análisis"):
            st.session_state["rol"] = "consulta"
            st.rerun()

# Si eligió analista, mostramos login
if st.session_state.get("modo_login") == "analista" and "rol" not in st.session_state:
    st.markdown("### 🔐 Ingreso de analista")
    clave = st.text_input("Ingresa la clave de acceso:", type="password")
    if clave == "epm2025":
        st.success("✅ Acceso concedido")
        st.session_state["rol"] = "admin"
        st.rerun()
    elif clave:
        st.error("❌ Clave incorrecta")


# Tarjetas de KPI
def tarjeta_kpi(titulo, valor, unidad=""):
    st.markdown(f"""
        <div style="background-color:#f2fdf5; border:2px solid #009739; border-radius:10px; padding:15px; text-align:center; margin-bottom:10px;">
            <h4 style="color:#009739; margin:0;">{titulo}</h4>
            <p style="font-size:1.5em; font-weight:bold; margin:5px 0;">{valor} {unidad}</p>
        </div>
    """, unsafe_allow_html=True)

# Badges de estado
def badge_estado(texto, color="#009739"):
    st.markdown(f"""
        <span style='background-color:{color}; color:white; padding:4px 8px; border-radius:12px; font-size:0.85em;'>{texto}</span>
    """, unsafe_allow_html=True)

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


# Mostrar logo en esquina superior izquierda con espacio
st.markdown(f"""
    <div style="position: absolute; top: 10px; left: 10px; z-index: 1000;">
        <img src="data:image/png;base64,{logo_base64}" width="110">
    </div>
    <br><br><br>
""", unsafe_allow_html=True)

st.markdown("""
    <div style='background-color:#009739; padding: 20px 10px; border-radius: 8px; text-align: center'>
        <h1 style='color: white; margin: 0;'>Análisis de Floculación</h1>
    </div>
    <br>
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

# Tabs principales
if st.session_state.get("rol") == "admin":
    tab_inicio, tab_ingreso, tab_procesar, tab_comparativos, tab_otros, tab_guardar, tab_historicos = st.tabs([
        "🏠 Inicio", "📥 Ingreso", "⚗️ Procesamiento", "📈 Comparativos", "📊 Otros", "💾 Guardar", "📂 Históricos"
    ])
elif st.session_state.get("rol") == "consulta":
    tab_consulta = st.tabs(["🔎 Consulta"])[0]
else:
    st.stop()

# ==== DEFINICIÓN DE FUNCIONES POR TAB (admin) ====

def mostrar_tab_inicio():
    with tab_inicio:
        st.markdown("## 🏠 Bienvenida al panel de control")
        col1, col2, col3 = st.columns(3)
        col1.metric("Mediciones totales", 1285)
        col2.metric("Último análisis", "2025-08-03")
        col3.metric("Plantas activas", 13)
        st.markdown("---")
        st.markdown("### 🔎 Accesos rápidos")
        col4, col5 = st.columns(2)
        with col4:
            if st.button("📥 Ir a Ingreso de datos"):
                st.markdown("*(Este botón podría activar un cambio de pestaña)*")
        with col5:
            if st.button("📂 Ir a Históricos"):
                st.markdown("*(O mostrar resumen de análisis recientes aquí mismo)*")

def mostrar_tab_ingreso():
with tab_consulta:
    st.markdown("## 🔎 Consulta de análisis por planta")

    cols = st.columns(4)
    for idx, planta in enumerate(PLANTAS):
        with cols[idx % 4]:
            img = Image.open(f"{CARPETA_PLANTAS}/{planta['archivo']}")
            if st.button(planta["nombre"], key=planta["nombre"]):
                st.session_state["planta_filtrada"] = planta["nombre"]
                st.session_state["rol"] = "consulta_historico"
                st.rerun()
            st.image(img, use_column_width=True)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📅 Buscar por fecha"):
            st.session_state["rol"] = "consulta_fecha"
            st.rerun()

    with col2:
        if st.button("🧪 Pruebas de desempeño"):
            st.info("🔧 Esta sección está en construcción.")



# 📥 INGRESO DE INFORMACIÓN
with tab_procesamiento:
    if st.session_state["procesado"]:
        mysql_password = st.session_state["mysql_password"]
        archivos = st.session_state["archivos"]
        planta = st.session_state["planta"]
        fecha_analisis = st.session_state["fecha_analisis"]
        notas = st.session_state["notas"]
        accion = st.session_state["accion"]

        conn = mysql.connector.connect(
            host="localhost", user="root",
            password=mysql_password,
            database="mediciones_db"
        )
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



            df_resumen = pd.DataFrame(resumen)
            df_resumen.to_csv(f"{output_folder}/resumen_mediciones_{fecha_analisis}_{planta}.csv", index=False)
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

	    # 🔄 Renombrar columnas para que coincidan con la base de datos
            df_resumen = df_resumen.rename(columns={
                "Di (mm)": "di",
                "Df (mm)": "df",
                "ΔD (mm)": "delta_d",
                "D(T) (mm)": "dt",
                "T_63 (s)": "t63"
            })

            # 💾 Guardar resumen en la tabla `historico`
            cursor = conn.cursor()
            for _, fila in df_resumen.iterrows():
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

            st.success("📦 Resumen guardado en la base de datos (tabla `historico`).")


            cursor.close()
            conn.close()

# 📈 COMPARATIVOS
with tab_graficos:
    st.subheader("📉 Visualización por variable")

    mysql_password = st.session_state.get("mysql_password", "")
    if mysql_password:
        conn = mysql.connector.connect(
            host="localhost", user="root", password=mysql_password, database="mediciones_db"
        )
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
        fig.savefig(f"{output_folder}/{nombre_archivo}")

        cursor.close()
        conn.close()

    else:
        st.warning("🔑 Ingresa tu contraseña en la pestaña 'Ingreso de información' para acceder a esta sección.")


# 💾 GUARDAR INFORMACIÓN

# ==== FUNCIONES DE CADA PESTAÑA ====

def mostrar_tab_ingreso():
    with tab_ingreso:
            # 📥 INGRESO DE INFORMACIÓN
            st.subheader("Ingreso de mediciones")
            # Aquí va tu lógica actual de ingreso (puedes copiarla del script original)
    def mostrar_tab_procesar():
        st.subheader("Ingreso de parámetros y carga de datos")
     # 🔁 Botón temporal para reiniciar estado (útil para desarrollo)
        if st.button("🧹 Resetear estado (debug)"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        mysql_password = st.text_input("🔐 Contraseña de MySQL", type="password")
        planta = st.text_input("🏭 Nombre de la planta")
        fecha_analisis = st.date_input("📅 Fecha del análisis", value=datetime.date.today())
        notas = st.text_area("📝 Comentarios del ensayo")
        archivos = st.file_uploader("📁 Subir archivo(s) CSV", type="csv", accept_multiple_files=True)
        accion = st.radio("¿Qué hacer con los datos anteriores?", ["Conservar", "Eliminar todo antes de cargar"])
        if st.button("🚀 Iniciar procesamiento") and mysql_password and archivos:
            st.session_state["procesado"] = True
            st.session_state["mysql_password"] = mysql_password
            st.session_state["archivos"] = archivos
            st.session_state["planta"] = planta
            st.session_state["fecha_analisis"] = fecha_analisis
            st.session_state["notas"] = notas
            st.session_state["accion"] = accion
    # 🔍 PROCESAMIENTO


def mostrar_tab_procesar():
    with tab_procesar:
            st.subheader("Procesamiento de datos")
            # Aquí va tu lógica de procesamiento (copiar del script original)
    def mostrar_tab_comparativos():


def mostrar_tab_comparativos():
    with tab_comparativos:
            st.subheader("Gráficos comparativos")
            # Aquí va tu lógica de comparación (copiar del script original)
    def mostrar_tab_otros():
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
            fig1.savefig(f"{output_folder}/grafico_coagulante_vs_t63_{planta_actual}_{fecha_str}.png")
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
                    fig2.savefig(f"{output_folder}/grafico_floculante_vs_t63_dc_{dc}.png")
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
                    fig3.savefig(f"{output_folder}/grafico_comparacion_floculante_{planta_actual}.png")
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
            fig4.savefig(f"{output_folder}/grafico_coagulante_vs_deltaD_{planta_actual}_{fecha_str}.png")
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
                    fig5.savefig(f"{output_folder}/grafico_floculante_vs_deltaD_dc_{dc}_{planta_actual}_{fecha_str}.png")
        else:
            st.warning("⚠️ Aún no se ha procesado ninguna medición. Procesa datos en la pestaña 'Procesamiento'.")
    # 📉 OTROS GRÁFICOS


def mostrar_tab_otros():
    with tab_otros:
            st.subheader("Otros indicadores")
            # Aquí va contenido extra si aplica
    def mostrar_tab_guardar():


def mostrar_tab_guardar():
    with tab_guardar:
            st.subheader("Guardar análisis")
            # Aquí va la lógica para guardar archivos/resultados
    def mostrar_tab_historicos():
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
    #HISTORICOS


def mostrar_tab_historicos():
    with tab_historicos:
            st.subheader("Históricos y consultas")
            # Aquí va la lógica de consulta histórica (copiar del script original)


def mostrar_tab_consulta():
    with tab_consulta:
        st.markdown("## 🔎 Consulta de análisis por planta")
        cols = st.columns(4)
        for idx, planta in enumerate(PLANTAS):
            with cols[idx % 4]:
                img = Image.open(f"{CARPETA_PLANTAS}/{planta['archivo']}")
                if st.button(planta["nombre"], key=planta["nombre"]):
                    st.session_state["planta_filtrada"] = planta["nombre"]
                    st.session_state["rol"] = "consulta_historico"
                    st.rerun()
                st.image(img, use_column_width=True)
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📅 Buscar por fecha"):
                st.session_state["rol"] = "consulta_fecha"
                st.rerun()
        with col2:
            if st.button("🧪 Pruebas de desempeño"):
                st.info("🔧 Esta sección está en construcción.")

