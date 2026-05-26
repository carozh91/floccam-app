# Floccam Analyzer

Aplicación de análisis de floculación para EPM.

## Ejecutar con Docker

1. Crea un archivo `.env` tomando como base `.env.example`.
2. Cambia `MYSQL_ROOT_PASSWORD` por una contraseña local.
3. Levanta la app:

```powershell
docker compose up --build
```

La nueva app queda disponible en:

```text
http://localhost:3000
```

La API queda disponible en:

```text
http://localhost:8000
```

El servicio MySQL se inicializa con `dump.sql` la primera vez que se crea el volumen `floccam_mysql_data`.

## Configuración de base de datos

El backend usa variables de entorno:

- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `MYSQL_PORT`

## Estructura

```text
backend/   API FastAPI y lógica de análisis
frontend/  Interfaz React
dump.sql   Datos iniciales para MySQL
```

`app_final2.py` queda como referencia temporal de la versión anterior mientras se completa la migración de todas las vistas.
