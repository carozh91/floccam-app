from datetime import date

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .analysis import MEDICIONES_COLUMNS, calculate_final_summary, parse_csv_bytes
from .database import bootstrap_database, db_connection, fetch_all


app = FastAPI(title="Floccam API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FinalMeasurement(BaseModel):
    nombre_medicion: str
    df: float
    series: list[dict]


class SaveAnalysisRequest(BaseModel):
    planta: str
    fecha: date
    mediciones: list[FinalMeasurement]
    replace_existing: bool = False


@app.on_event("startup")
def startup() -> None:
    bootstrap_database()


@app.get("/health")
def health() -> dict:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
    return {"status": "ok"}


@app.get("/plants")
def list_plants() -> list[str]:
    rows = fetch_all("SELECT DISTINCT planta FROM historico WHERE planta IS NOT NULL ORDER BY planta")
    return [row["planta"] for row in rows]


@app.get("/plants/{planta}/dates")
def list_dates(planta: str) -> list[str]:
    rows = fetch_all(
        "SELECT DISTINCT fecha FROM historico WHERE planta = %s ORDER BY fecha DESC",
        (planta,),
    )
    return [row["fecha"].isoformat() for row in rows]


@app.get("/history")
def get_history(planta: str | None = None, fecha: date | None = None) -> list[dict]:
    query = "SELECT * FROM historico"
    params: list = []
    filters = []
    if planta:
        filters.append("planta = %s")
        params.append(planta)
    if fecha:
        filters.append("fecha = %s")
        params.append(fecha)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY fecha DESC, planta, nombre_medicion"
    rows = fetch_all(query, tuple(params))
    for row in rows:
        if row.get("fecha"):
            row["fecha"] = row["fecha"].isoformat()
    return rows


@app.post("/analysis/preview")
async def preview_analysis(
    files: list[UploadFile] = File(...),
    clear_measurements: bool = Form(False),
) -> dict:
    parsed = []
    errors = []

    for uploaded in files:
        try:
            parsed.append(parse_csv_bytes(uploaded.filename, await uploaded.read()))
        except Exception as exc:
            errors.append({"file": uploaded.filename, "message": str(exc)})

    if not parsed and errors:
        raise HTTPException(status_code=422, detail=errors)

    with db_connection() as conn:
        cursor = conn.cursor()
        if clear_measurements:
            cursor.execute("DELETE FROM mediciones")

        placeholders = ", ".join(["%s"] * len(MEDICIONES_COLUMNS))
        columns = ", ".join(MEDICIONES_COLUMNS)
        insert_sql = f"INSERT INTO mediciones ({columns}) VALUES ({placeholders})"

        for measurement in parsed:
            values = []
            for row in measurement.rows:
                row_dict = dict(zip(
                    [
                        "ascii_time", "excel_time", "unix_time", "diameter", "number", "mass_fraction",
                        "skew1", "skew2", "skew3", "fractal_dimension", "sphericity", "clarity",
                        "brightness", "sizea", "sizev", "size01", "size02", "size03", "dividersize",
                        "aveaspectv", "avewidthv", "avelengthv", "largestfloc",
                    ],
                    row,
                ))
                values.append((
                    measurement.name,
                    row_dict["unix_time"],
                    row_dict["diameter"],
                    row_dict["number"],
                    row_dict["mass_fraction"],
                    row_dict["skew1"],
                    row_dict["skew2"],
                    row_dict["skew3"],
                    row_dict["fractal_dimension"],
                    row_dict["sphericity"],
                    row_dict["clarity"],
                    row_dict["largestfloc"],
                ))
            if values:
                cursor.executemany(insert_sql, values)

        conn.commit()
        cursor.close()

    return {
        "measurements": [
            {"summary": item.summary, "series": item.series}
            for item in parsed
        ],
        "errors": errors,
    }


@app.post("/analysis/save")
def save_analysis(payload: SaveAnalysisRequest) -> dict:
    if not payload.mediciones:
        raise HTTPException(status_code=422, detail="No hay mediciones para guardar.")

    summaries = [
        calculate_final_summary(item.nombre_medicion, item.series, item.df)
        for item in payload.mediciones
    ]

    with db_connection() as conn:
        cursor = conn.cursor()
        if payload.replace_existing:
            cursor.execute(
                "DELETE FROM historico WHERE planta = %s AND fecha = %s",
                (payload.planta, payload.fecha),
            )

        cursor.executemany(
            """
            INSERT INTO historico (
                nombre_medicion, fecha, planta, di, df, delta_d, dt, t63,
                dosis_coagulante, dosis_floculante
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["nombre_medicion"],
                    payload.fecha,
                    payload.planta,
                    row["di"],
                    row["df"],
                    row["delta_d"],
                    row["dt"],
                    row["t63"],
                    row["dosis_coagulante"],
                    row["dosis_floculante"],
                )
                for row in summaries
            ],
        )
        conn.commit()
        cursor.close()

    return {"saved": len(summaries), "summaries": summaries}


@app.delete("/history")
def delete_all_history() -> dict:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico")
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
    return {"deleted": affected}


@app.delete("/history/{record_id}")
def delete_history_record(record_id: int) -> dict:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico WHERE id = %s", (record_id,))
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
    return {"deleted": affected}
