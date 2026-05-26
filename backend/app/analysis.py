import io
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd


MEASUREMENT_COLUMNS = [
    "ascii_time",
    "excel_time",
    "unix_time",
    "diameter",
    "number",
    "mass_fraction",
    "skew1",
    "skew2",
    "skew3",
    "fractal_dimension",
    "sphericity",
    "clarity",
    "brightness",
    "sizea",
    "sizev",
    "size01",
    "size02",
    "size03",
    "dividersize",
    "aveaspectv",
    "avewidthv",
    "avelengthv",
    "largestfloc",
]

MEDICIONES_COLUMNS = [
    "nombre_medicion",
    "unix_time",
    "diameter",
    "number",
    "mass_fraction",
    "skew1",
    "skew2",
    "skew3",
    "fractal_dimension",
    "sphericity",
    "clarity",
    "largestfloc",
]


@dataclass
class ParsedMeasurement:
    name: str
    rows: list[tuple]
    summary: dict
    series: list[dict]


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\W+", "_", col.strip().lower()) for col in df.columns]
    return df


def parse_doses_from_name(name: str) -> tuple[float | None, float | None]:
    parts = name.rsplit("_", 2)
    if len(parts) < 3:
        return None, None
    try:
        coagulant = float(parts[-2].replace(",", "."))
        flocculant = float(parts[-1].replace(",", "."))
    except ValueError:
        return None, None
    return coagulant, flocculant


def parse_csv_bytes(filename: str, content: bytes) -> ParsedMeasurement:
    name = re.sub(r"\.[^.]+$", "", filename)
    coagulant_dose, flocculant_dose = parse_doses_from_name(name)
    df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    if df.empty:
        raise ValueError(f"{filename} no contiene datos.")

    df = normalize_columns(df)
    missing = [col for col in MEASUREMENT_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"{filename} no contiene columnas requeridas: {', '.join(missing[:8])}")

    df = df[MEASUREMENT_COLUMNS].replace({np.nan: None})
    series_df = df[["unix_time", "diameter", "clarity", "mass_fraction", "fractal_dimension", "largestfloc"]].dropna(
        subset=["unix_time", "diameter"]
    )
    series_df = series_df.sort_values("unix_time")

    if series_df.empty:
        raise ValueError(f"{filename} no contiene datos suficientes para graficar.")

    start_time = float(series_df["unix_time"].iloc[0])
    series_df["time"] = series_df["unix_time"].astype(float) - start_time
    diameters = series_df["diameter"].astype(float).to_numpy()
    times = series_df["time"].astype(float).to_numpy()

    di = float(diameters[0])
    suggested_df = float(diameters[-1])
    dt = float(diameters.max())
    target = di + 0.63 * (suggested_df - di)
    idx_t63 = int(np.abs(diameters - target).argmin())
    t63 = float(times[idx_t63])

    summary = {
        "nombre_medicion": name,
        "di": di,
        "df_sugerido": suggested_df,
        "delta_d_sugerido": suggested_df - di,
        "dt": dt,
        "t63_sugerido": t63,
        "puntos": int(len(series_df)),
        "dosis_coagulante": coagulant_dose,
        "dosis_floculante": flocculant_dose,
    }

    rows = []
    for row in df.itertuples(index=False, name=None):
        rows.append(tuple(row))

    series = [
        {
            "time": float(row["time"]),
            "diameter": float(row["diameter"]),
            "clarity": None if pd.isna(row["clarity"]) else float(row["clarity"]),
            "mass_fraction": None if pd.isna(row["mass_fraction"]) else float(row["mass_fraction"]),
            "fractal_dimension": None if pd.isna(row["fractal_dimension"]) else float(row["fractal_dimension"]),
            "largestfloc": None if pd.isna(row["largestfloc"]) else float(row["largestfloc"]),
        }
        for _, row in series_df.iterrows()
    ]

    return ParsedMeasurement(name=name, rows=rows, summary=summary, series=series)


def calculate_final_summary(name: str, series: list[dict], df_value: float) -> dict:
    diameters = np.array([point["diameter"] for point in series], dtype=float)
    times = np.array([point["time"] for point in series], dtype=float)
    coagulant_dose, flocculant_dose = parse_doses_from_name(name)
    di = float(diameters[0])
    delta_d = float(df_value - di)
    target = di + 0.63 * delta_d
    idx_t63 = int(np.abs(diameters - target).argmin())
    return {
        "nombre_medicion": name,
        "di": di,
        "df": float(df_value),
        "delta_d": delta_d,
        "dt": float(diameters.max()),
        "t63": float(times[idx_t63]),
        "dosis_coagulante": coagulant_dose,
        "dosis_floculante": flocculant_dose,
    }
