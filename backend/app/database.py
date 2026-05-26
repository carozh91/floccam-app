import os
from contextlib import contextmanager

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool


def _db_config() -> dict:
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "mediciones_db"),
        "autocommit": False,
    }


_pool: MySQLConnectionPool | None = None


def get_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = MySQLConnectionPool(pool_name="floccam_pool", pool_size=5, **_db_config())
    return _pool


@contextmanager
def db_connection():
    conn = get_pool().get_connection()
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows


def bootstrap_database() -> None:
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS medicion_temp (
          ascii_time varchar(50) DEFAULT NULL,
          excel_time varchar(50) DEFAULT NULL,
          unix_time double DEFAULT NULL,
          diameter double DEFAULT NULL,
          number int DEFAULT NULL,
          mass_fraction double DEFAULT NULL,
          skew1 double DEFAULT NULL,
          skew2 double DEFAULT NULL,
          skew3 double DEFAULT NULL,
          fractal_dimension double DEFAULT NULL,
          sphericity double DEFAULT NULL,
          clarity double DEFAULT NULL,
          brightness double DEFAULT NULL,
          sizea double DEFAULT NULL,
          sizev double DEFAULT NULL,
          size01 double DEFAULT NULL,
          size02 double DEFAULT NULL,
          size03 double DEFAULT NULL,
          dividersize double DEFAULT NULL,
          aveaspectv double DEFAULT NULL,
          avewidthv double DEFAULT NULL,
          avelengthv double DEFAULT NULL,
          largestfloc double DEFAULT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mediciones (
          id int NOT NULL AUTO_INCREMENT,
          nombre_medicion varchar(255) DEFAULT NULL,
          unix_time double DEFAULT NULL,
          diameter double DEFAULT NULL,
          number int DEFAULT NULL,
          mass_fraction double DEFAULT NULL,
          skew1 double DEFAULT NULL,
          skew2 double DEFAULT NULL,
          skew3 double DEFAULT NULL,
          fractal_dimension double DEFAULT NULL,
          sphericity double DEFAULT NULL,
          clarity double DEFAULT NULL,
          largestfloc double DEFAULT NULL,
          PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS historico (
          id int NOT NULL AUTO_INCREMENT,
          fecha date DEFAULT NULL,
          planta varchar(100) DEFAULT NULL,
          nombre_medicion varchar(255) DEFAULT NULL,
          di float DEFAULT NULL,
          df float DEFAULT NULL,
          delta_d float DEFAULT NULL,
          dt float DEFAULT NULL,
          t63 float DEFAULT NULL,
          dosis_coagulante float DEFAULT NULL,
          dosis_floculante float DEFAULT NULL,
          PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS graficos (
          id int NOT NULL AUTO_INCREMENT,
          planta varchar(100) NOT NULL,
          fecha date NOT NULL,
          nombre_medicion varchar(255) NOT NULL,
          tipo varchar(80) DEFAULT NULL,
          nombre_archivo varchar(255) NOT NULL,
          formato varchar(10) DEFAULT 'PNG',
          imagen_blob longblob NOT NULL,
          ancho int DEFAULT NULL,
          alto int DEFAULT NULL,
          creado_en timestamp DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id)
        )
        """,
    ]
    indexes = [
        "CREATE INDEX idx_historico_planta_fecha ON historico(planta, fecha)",
        "CREATE INDEX idx_graficos_lookup ON graficos(planta, fecha, tipo, nombre_medicion)",
    ]
    migrations = [
        "ALTER TABLE historico ADD COLUMN dosis_coagulante float DEFAULT NULL",
        "ALTER TABLE historico ADD COLUMN dosis_floculante float DEFAULT NULL",
    ]
    backfills = [
        """
        UPDATE historico
        SET
          dosis_coagulante = CAST(REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(nombre_medicion, '_', -2), '_', 1), ',', '.') AS DECIMAL(10, 4)),
          dosis_floculante = CAST(REPLACE(SUBSTRING_INDEX(nombre_medicion, '_', -1), ',', '.') AS DECIMAL(10, 4))
        WHERE
          (dosis_coagulante IS NULL OR dosis_floculante IS NULL)
          AND nombre_medicion REGEXP '_[0-9]+([.][0-9]+)?_[0-9]+([.][0-9]+)?$'
        """,
    ]

    with db_connection() as conn:
        cursor = conn.cursor()
        for statement in ddl:
            cursor.execute(statement)
        for statement in migrations:
            try:
                cursor.execute(statement)
            except mysql.connector.Error:
                pass
        for statement in backfills:
            cursor.execute(statement)
        for statement in indexes:
            try:
                cursor.execute(statement)
            except mysql.connector.Error:
                pass
        conn.commit()
        cursor.close()
