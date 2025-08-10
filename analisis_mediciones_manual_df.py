import pandas as pd
import matplotlib.pyplot as plt
import mysql.connector
from getpass import getpass
import os

# Conexión a MySQL
conexion = mysql.connector.connect(
    host="localhost",
    user="root",
    password=getpass("🔐 Ingresa la contraseña de MySQL: "),
    database="mediciones_db"
)
cursor = conexion.cursor()

# Crear carpeta de gráficos si no existe
os.makedirs("graficos_mediciones", exist_ok=True)

# Obtener nombres únicos de las mediciones
cursor.execute("SELECT DISTINCT nombre_medicion FROM mediciones")
mediciones = [row[0] for row in cursor.fetchall()]

# Preparar resultados
resultados = []

# Procesar cada medición
for nombre in mediciones:
    cursor.execute("""
        SELECT unix_time, diameter 
        FROM mediciones 
        WHERE nombre_medicion = %s 
        ORDER BY unix_time ASC
    """, (nombre,))
    datos = cursor.fetchall()
    
    if not datos:
        continue

    # Crear DataFrame y calcular tiempo relativo
    df = pd.DataFrame(datos, columns=["unix_time", "diameter"])
    df["tiempo"] = df["unix_time"] - df["unix_time"].iloc[0]

    # Di: primer valor de diámetro
    Di = df["diameter"].iloc[0]

    # Mostrar gráfica para selección de Df
    plt.figure(figsize=(10, 6))
    plt.scatter(df["tiempo"], df["diameter"], label="Diámetro")
    plt.title(f"{nombre} - Selección manual de Df")
    plt.xlabel("Tiempo (s)")
    plt.ylabel("Diámetro (mm)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f"graficos_mediciones/{nombre}_grafico.png")
    plt.show()

    try:
        Df = float(input(f"Ingrese el valor de Df (observado en la gráfica para {nombre}): "))
    except:
        print("❌ Valor inválido. Se omite esta medición.")
        continue

    delta_D = Df - Di
    D_T = Di + 0.632 * delta_D

    # Buscar el tiempo más cercano a D(T)
    df["diff"] = abs(df["diameter"] - D_T)
    T63 = df.loc[df["diff"].idxmin()]["tiempo"]

    resultados.append({
        "nombre_medicion": nombre,
        "Di (mm)": round(Di, 4),
        "Df (mm)": round(Df, 4),
        "ΔD (mm)": round(delta_D, 4),
        "D(T) (mm)": round(D_T, 4),
        "T_63 (s)": round(T63, 2)
    })

# Guardar resumen en CSV
df_resultados = pd.DataFrame(resultados)
df_resultados.to_csv("resumen_mediciones.csv", index=False)

print("✅ Análisis finalizado. Resultados guardados en 'resumen_mediciones.csv' y gráficos en 'graficos_mediciones/'.")