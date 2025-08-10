import pandas as pd
import mysql.connector
import os

# 🟡 Paso 1: Solicita datos al usuario
password = input("🔐 Ingresa tu contraseña de MySQL:\n")
rutas_input = input("📂 Ingresa las rutas completas de los archivos CSV que deseas cargar, separados por coma:\n")

# Limpia las rutas y separa los archivos
rutas_archivos = [ruta.strip().strip('"') for ruta in rutas_input.split(',')]

# 🟡 Paso 2: Conecta a la base de datos
try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=password,
        database="mediciones_db"
    )
    cursor = conn.cursor()
except Exception as e:
    print(f"❌ Error al conectar a MySQL: {e}")
    exit()

# ✅ Columnas esperadas para la tabla `medicion_temp`
columnas_medicion_temp = [
    'ascii_time', 'excel_time', 'unix_time', 'diameter', 'number',
    'mass_fraction', 'skew1', 'skew2', 'skew3', 'fractal_dimension',
    'sphericity', 'clarity', 'brightness', 'sizea', 'sizev',
    'size01', 'size02', 'size03', 'dividersize',
    'aveaspectv', 'avewidthv', 'avelengthv', 'largestfloc'
]

# ✅ Columnas para insertar en la tabla `mediciones` (12 + nombre_medicion)
columnas_mediciones = [
    'nombre_medicion', 'unix_time', 'diameter', 'number',
    'mass_fraction', 'skew1', 'skew2', 'skew3', 'fractal_dimension',
    'sphericity', 'clarity', 'largestfloc'
]

# 🟢 Paso 3: Procesa cada archivo CSV
for ruta_csv in rutas_archivos:
    try:
        if not os.path.isfile(ruta_csv):
            print(f"❌ El archivo {ruta_csv} no existe.")
            continue

        # 🟢 3.1. Carga el CSV con normalización de columnas
        df = pd.read_csv(ruta_csv)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

        # 🟢 3.2. Verifica que tenga todas las columnas requeridas para `medicion_temp`
        if not all(col in df.columns for col in columnas_medicion_temp):
            print(f"❌ El archivo {os.path.basename(ruta_csv)} no contiene todas las columnas requeridas.")
            continue

        # 🟢 3.3. Inserta los datos en la tabla `medicion_temp`
        cursor.execute("DELETE FROM medicion_temp")
        conn.commit()

        columnas_str = ', '.join(columnas_medicion_temp)
        placeholders = ', '.join(['%s'] * len(columnas_medicion_temp))

        insert_temp_sql = f"INSERT INTO medicion_temp ({columnas_str}) VALUES ({placeholders})"
        valores = df[columnas_medicion_temp].values.tolist()

        cursor.executemany(insert_temp_sql, valores)
        conn.commit()

        # 🟢 3.4. Inserta desde `medicion_temp` a `mediciones`, usando el nombre del archivo como nombre_medicion
        nombre_medicion = os.path.splitext(os.path.basename(ruta_csv))[0]

        insert_mediciones_sql = f"""
            INSERT INTO mediciones (
                nombre_medicion, unix_time, diameter, number,
                mass_fraction, skew1, skew2, skew3, fractal_dimension,
                sphericity, clarity, largestfloc
            )
            SELECT
                %s, unix_time, diameter, number,
                mass_fraction, skew1, skew2, skew3, fractal_dimension,
                sphericity, clarity, largestfloc
            FROM medicion_temp
        """
        cursor.execute(insert_mediciones_sql, (nombre_medicion,))
        conn.commit()

        # 🟢 3.5. Limpia la tabla `medicion_temp`
        cursor.execute("DELETE FROM medicion_temp")
        conn.commit()

        print(f"✅ Datos insertados exitosamente desde: {ruta_csv}")

    except Exception as e:
        print(f"❌ Error al insertar los datos desde {ruta_csv}: {e}")

# 🟢 Paso 4: Cierra la conexión
cursor.close()
conn.close()
print("✅ Todos los archivos fueron procesados.")
