import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import mysql.connector
import re
import os

# Configuración de carpeta
output_folder = "graficos_mediciones"
os.makedirs(output_folder, exist_ok=True)

# Conexión MySQL
conexion = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Emanuel10*",  # Cambia si es necesario
    database="mediciones_db"
)
cursor = conexion.cursor(dictionary=True)
cursor.execute("SELECT * FROM mediciones")
registros = cursor.fetchall()
df = pd.DataFrame(registros)

# Agrupar por nombre_medicion
resumen = []

for nombre, grupo in df.groupby("nombre_medicion"):
    grupo = grupo.sort_values("unix_time")
    unix = grupo["unix_time"].to_numpy()
    diam = grupo["diameter"].to_numpy()

    if len(diam) == 0:
        continue

    di = diam[0]

    # Mostrar gráfico para entrada manual
    plt.figure(figsize=(8, 5))
    plt.plot(unix, diam, marker="o")
    plt.title(f"[{nombre}] Diámetro vs Tiempo")
    plt.xlabel("Tiempo (s)")
    plt.ylabel("Diámetro (mm)")
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    try:
        df_manual = float(input(f"Ingrese el valor de Df para '{nombre}': "))
    except ValueError:
        print("❌ Entrada inválida. Se omite esta medición.")
        continue

    delta_d = df_manual - di
    d_t = diam.max()

    # Calcular T_63 basado en Df manual
    objetivo = di + 0.63 * (df_manual - di)
    dif_abs = np.abs(diam - objetivo)
    idx_t63 = dif_abs.argmin()
    t_63 = unix[idx_t63] if len(unix) > idx_t63 else np.nan

    resumen.append({
        "nombre_medicion": nombre,
        "Di (mm)": di,
        "Df (mm)": df_manual,
        "ΔD (mm)": delta_d,
        "D(T) (mm)": d_t,
        "T_63 (s)": t_63
    })

    # Guardar gráfico con líneas
    plt.figure(figsize=(8, 5))
    plt.plot(unix, diam, marker="o")
    plt.axhline(objetivo, color="red", linestyle="--", label="63% ΔD")
    plt.axvline(t_63, color="green", linestyle="--", label="T_63")
    plt.title(f"Diámetro vs Tiempo\n{nombre}")
    plt.xlabel("Tiempo (s)")
    plt.ylabel("Diámetro (mm)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f"{output_folder}/{nombre}_grafico.png")
    plt.close()

# Guardar CSV resumen
df_resumen = pd.DataFrame(resumen)
df_resumen.to_csv("resumen_mediciones.csv", index=False)

# ========================================================
# GRÁFICOS DE COMPARACIÓN: Dosis vs T_63
# ========================================================

# Extraer dosis desde nombre_medicion (patrón: AAAA-MM-DD_nombre_XX_YY)
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

# Eliminar filas con dosis faltantes
df_resumen = df_resumen.dropna(subset=['dosis_coagulante', 'dosis_floculante', 'T_63 (s)'])

# Gráfico 1: Coagulante vs T_63 para cada floculante fijo
for floc in sorted(df_resumen['dosis_floculante'].unique()):
    sub = df_resumen[df_resumen['dosis_floculante'] == floc]
    if len(sub) >= 2:
        plt.figure(figsize=(8, 5))
        plt.plot(sub['dosis_coagulante'], sub['T_63 (s)'], marker='o', linestyle='--', color='blue')
        plt.xlabel("Dosis de Coagulante (ppm)")
        plt.ylabel("T_63 (s)")
        plt.title(f"Coagulante vs T_63 (Floculante = {floc})")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(f"{output_folder}/coagulante_vs_T63_floc_{floc}.png")
        plt.close()

# Gráfico 2: Floculante vs T_63 para cada coagulante fijo
for coag in sorted(df_resumen['dosis_coagulante'].unique()):
    sub = df_resumen[df_resumen['dosis_coagulante'] == coag]
    if len(sub['dosis_floculante'].unique()) >= 2:
        plt.figure(figsize=(8, 5))
        plt.plot(sub['dosis_floculante'], sub['T_63 (s)'], marker='o', linestyle='--', color='green')
        plt.xlabel("Dosis de Floculante (ppm)")
        plt.ylabel("T_63 (s)")
        plt.title(f"Floculante vs T_63 (Coagulante = {coag})")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(f"{output_folder}/floculante_vs_T63_coag_{coag}.png")
        plt.close()

# Gráfico 3: Comparativo de curvas de coagulante vs T_63 para distintas dosis de floculante
floculantes_disponibles = sorted(df_resumen['dosis_floculante'].unique())
if len(floculantes_disponibles) > 1:
    plt.figure(figsize=(10, 6))
    colores = plt.cm.plasma(np.linspace(0, 1, len(floculantes_disponibles)))
    for i, floc in enumerate(floculantes_disponibles):
        sub = df_resumen[df_resumen['dosis_floculante'] == floc]
        if len(sub) >= 2:
            plt.plot(sub['dosis_coagulante'], sub['T_63 (s)'], marker='o', label=f"Floc = {floc}", color=colores[i])
    plt.xlabel("Dosis de Coagulante (ppm)")
    plt.ylabel("T_63 (s)")
    plt.title("Comparación de curvas: Coagulante vs T_63 para distintos floculantes")
    plt.legend(title="Dosis Floculante")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f"{output_folder}/comparacion_coagulante_vs_T63.png")
    plt.close()
