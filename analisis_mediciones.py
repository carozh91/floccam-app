
import mysql.connector
import pandas as pd
import matplotlib.pyplot as plt
import os

# Conexión a la base de datos
conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='Emanuel10*',
    database='mediciones_db'
)

# Obtener todas las mediciones distintas
df_all = pd.read_sql("SELECT * FROM mediciones", conn)
mediciones = df_all['nombre_medicion'].unique()

resultados = []

# Crear carpeta para gráficos si no existe
os.makedirs("graficos_mediciones", exist_ok=True)

for medicion in mediciones:
    df = df_all[df_all['nombre_medicion'] == medicion].copy()
    df = df.sort_values(by='unix_time')
    df['tiempo'] = df['unix_time'] - df['unix_time'].iloc[0]

    # Di: primer valor
    Di = df['diameter'].iloc[0]

    # Opción A (simple): Df como el valor donde los 2 siguientes sean menores
    Df = None
    for i in range(len(df) - 2):
        if df['diameter'].iloc[i+1] < df['diameter'].iloc[i] and df['diameter'].iloc[i+2] < df['diameter'].iloc[i]:
            Df = df['diameter'].iloc[i]
            break

    if Df is None:
        print(f"No se encontró Df para {medicion}, se omite.")
        continue

    delta_D = Df - Di
    D_T = Di + 0.632 * delta_D

    # Buscar T_63
    df['diferencia'] = abs(df['diameter'] - D_T)
    idx_T63 = df['diferencia'].idxmin()
    T_63 = df.loc[idx_T63, 'tiempo']

    # Guardar gráfico
    plt.figure(figsize=(10, 6))
    plt.scatter(df['tiempo'], df['diameter'], label=medicion, color='blue', s=15)
    plt.axhline(D_T, color='red', linestyle='--', label=f'D(T) = {D_T:.3f}')
    plt.axvline(T_63, color='green', linestyle='--', label=f'T = {T_63:.1f} s')
    plt.title(f'Dispersión Tiempo vs Diámetro - {medicion}')
    plt.xlabel('Tiempo (s)')
    plt.ylabel('Diámetro (mm)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f'graficos_mediciones/{medicion}.png')
    plt.close()

    # Guardar resultado
    resultados.append({
        'nombre_medicion': medicion,
        'Di': round(Di, 4),
        'Df': round(Df, 4),
        'delta_D': round(delta_D, 4),
        'D_T': round(D_T, 4),
        'T_63 (s)': round(T_63, 2)
    })

# Crear DataFrame resumen y guardar como CSV
df_resumen = pd.DataFrame(resultados)
df_resumen.to_csv('resumen_mediciones.csv', index=False)
print("✅ Análisis completado. Ver resumen_mediciones.csv y carpeta graficos_mediciones/")
