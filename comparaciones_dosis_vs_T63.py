import pandas as pd
import matplotlib.pyplot as plt
import re

# Leer archivo de resumen
df = pd.read_csv("resumen_mediciones.csv")

# Función para extraer las dosis desde el nombre de la medición
def extraer_dosis(nombre):
    match = re.search(r"_(\d+)_([\d.]+)$", nombre)
    if match:
        return int(match.group(1)), float(match.group(2))
    return None, None

# Aplicar extracción de dosis
df[['dosis_coagulante', 'dosis_floculante']] = df['nombre_medicion'].apply(
    lambda x: pd.Series(extraer_dosis(x))
)

# --- GRÁFICO 1: COAGULANTE VS T63 (cuando floculante = 0) ---
df_coag = df[df['dosis_floculante'] == 0]

if not df_coag.empty:
    plt.figure(figsize=(8, 5))
    plt.scatter(df_coag['dosis_coagulante'], df_coag['T63'], color='blue', label='T63')
    plt.plot(df_coag['dosis_coagulante'], df_coag['T63'], linestyle='--', color='gray', alpha=0.7)
    plt.xlabel("Dosis de Coagulante (ppm)")
    plt.ylabel("T63 (s)")
    plt.title("Dosis de Coagulante vs T63 (Floculante = 0)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("coagulante_vs_T63.png")
    plt.show()
else:
    print("⚠️ No hay mediciones con floculante = 0")

# --- GRÁFICO 2: FLOCULANTE VS T63 (cuando coagulante es constante) ---
dosis_mas_frecuente = df['dosis_coagulante'].mode()[0]
df_floc = df[df['dosis_coagulante'] == dosis_mas_frecuente]

if not df_floc.empty:
    plt.figure(figsize=(8, 5))
    plt.scatter(df_floc['dosis_floculante'], df_floc['T63'], color='green', label='T63')
    plt.plot(df_floc['dosis_floculante'], df_floc['T63'], linestyle='--', color='gray', alpha=0.7)
    plt.xlabel("Dosis de Floculante (ppm)")
    plt.ylabel("T63 (s)")
    plt.title(f"Dosis de Floculante vs T63 (Coagulante = {dosis_mas_frecuente} ppm)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("floculante_vs_T63.png")
    plt.show()
else:
    print(f"⚠️ No hay mediciones con coagulante = {dosis_mas_frecuente} ppm")