import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Database,
  FileUp,
  FlaskConical,
  History,
  LineChart,
  RefreshCw,
  Save,
  Trash2,
  UploadCloud,
} from "lucide-react";
import "./styles.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function fileLabel(files) {
  if (!files.length) return "Selecciona uno o varios CSV";
  if (files.length === 1) return files[0].name;
  return `${files.length} archivos seleccionados`;
}

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    let detail = await response.text();
    try {
      detail = JSON.parse(detail).detail || detail;
    } catch {
      // Keep raw response text.
    }
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.message).join("\n") : detail);
  }
  return response.json();
}

function MiniChart({ series, variable = "diameter" }) {
  const points = useMemo(() => {
    const clean = (series || []).filter((point) => point[variable] !== null && point[variable] !== undefined);
    if (!clean.length) return "";

    const xs = clean.map((point) => Number(point.time));
    const ys = clean.map((point) => Number(point[variable]));
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const width = 640;
    const height = 220;
    const pad = 22;

    return clean
      .map((point) => {
        const x = maxX === minX ? width / 2 : pad + ((Number(point.time) - minX) / (maxX - minX)) * (width - pad * 2);
        const y = maxY === minY ? height / 2 : height - pad - ((Number(point[variable]) - minY) / (maxY - minY)) * (height - pad * 2);
        return `${x},${y}`;
      })
      .join(" ");
  }, [series, variable]);

  return (
    <div className="chart-frame">
      <svg viewBox="0 0 640 220" role="img" aria-label="Curva de medición">
        <line x1="22" y1="198" x2="618" y2="198" />
        <line x1="22" y1="22" x2="22" y2="198" />
        {points && <polyline points={points} />}
      </svg>
    </div>
  );
}

function ComparisonChart({ title, xLabel, yLabel = "T63 (s)", series }) {
  const colors = ["#08743b", "#2f6f9f", "#9a5b13", "#8a3ffc", "#b3261e", "#4f6f52"];
  const allPoints = series.flatMap((item) => item.points);
  if (!allPoints.length) {
    return (
      <article className="comparison-card">
        <h3>{title}</h3>
        <div className="comparison-empty">No hay suficientes datos con dosis para este comparativo.</div>
      </article>
    );
  }

  const xs = allPoints.map((point) => point.x);
  const ys = allPoints.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = 640;
  const height = 260;
  const pad = 38;
  const scaleX = (value) => (maxX === minX ? width / 2 : pad + ((value - minX) / (maxX - minX)) * (width - pad * 2));
  const scaleY = (value) => (maxY === minY ? height / 2 : height - pad - ((value - minY) / (maxY - minY)) * (height - pad * 2));

  return (
    <article className="comparison-card">
      <h3>{title}</h3>
      <div className="comparison-chart">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} />
          <line x1={pad} y1={pad} x2={pad} y2={height - pad} />
          <text x={width / 2} y={height - 6}>{xLabel}</text>
          <text x="8" y="22">{yLabel}</text>
          <text x={pad} y={height - 14}>{formatNumber(minX, 2)}</text>
          <text x={width - pad - 28} y={height - 14}>{formatNumber(maxX, 2)}</text>
          {series.map((item, index) => {
            const sorted = [...item.points].sort((a, b) => a.x - b.x);
            const points = sorted.map((point) => `${scaleX(point.x)},${scaleY(point.y)}`).join(" ");
            return (
              <g key={item.label}>
                {points && <polyline points={points} style={{ stroke: colors[index % colors.length] }} />}
                {sorted.map((point) => (
                  <circle
                    cx={scaleX(point.x)}
                    cy={scaleY(point.y)}
                    fill={colors[index % colors.length]}
                    key={`${item.label}-${point.name}-${point.x}-${point.y}`}
                    r="4"
                  />
                ))}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="legend">
        {series.map((item, index) => (
          <span key={item.label}>
            <i style={{ background: colors[index % colors.length] }} />
            {item.label}
          </span>
        ))}
      </div>
    </article>
  );
}

function Metric({ label, value, unit }) {
  const hasUnit = unit && value !== "-";
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>
        {value}
        {hasUnit && <small>{unit}</small>}
      </strong>
    </div>
  );
}

function Notice({ notice }) {
  if (!notice?.text) return null;
  const Icon = notice.type === "error" ? AlertCircle : CheckCircle2;
  return (
    <div className={`message ${notice.type || "info"}`}>
      <Icon size={18} />
      <span>{notice.text}</span>
    </div>
  );
}

function App() {
  const [status, setStatus] = useState("checking");
  const [files, setFiles] = useState([]);
  const [planta, setPlanta] = useState("");
  const [fecha, setFecha] = useState(today());
  const [clearMeasurements, setClearMeasurements] = useState(false);
  const [preview, setPreview] = useState([]);
  const [dfValues, setDfValues] = useState({});
  const [history, setHistory] = useState([]);
  const [plants, setPlants] = useState([]);
  const [selectedPlant, setSelectedPlant] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const analysisTotals = useMemo(() => {
    const measurements = preview.length;
    const points = preview.reduce((sum, item) => sum + Number(item.summary.puntos || 0), 0);
    const suggestedT63 = preview
      .map((item) => Number(item.summary.t63_sugerido))
      .filter((value) => !Number.isNaN(value));
    const avgT63 = suggestedT63.length
      ? suggestedT63.reduce((sum, value) => sum + value, 0) / suggestedT63.length
      : null;
    return { measurements, points, avgT63 };
  }, [preview]);

  const comparisons = useMemo(() => {
    const validRows = history
      .map((row) => ({
        ...row,
        doseC: Number(row.dosis_coagulante),
        doseF: Number(row.dosis_floculante),
        t63Value: Number(row.t63),
      }))
      .filter((row) => Number.isFinite(row.doseC) && Number.isFinite(row.doseF) && Number.isFinite(row.t63Value));

    const byKey = (rows, keyFn) =>
      rows.reduce((groups, row) => {
        const key = keyFn(row);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(row);
        return groups;
      }, new Map());

    const coagulantZeroFloc = Array.from(byKey(validRows.filter((row) => row.doseF === 0), (row) => row.planta))
      .map(([plant, rows]) => ({
        label: plant,
        points: rows.map((row) => ({ x: row.doseC, y: row.t63Value, name: row.nombre_medicion })),
      }))
      .filter((item) => item.points.length > 1);

    const flocculantFixedCoagulant = Array.from(byKey(validRows, (row) => `${row.planta} | C ${row.doseC}`))
      .map(([label, rows]) => ({
        label,
        points: rows.map((row) => ({ x: row.doseF, y: row.t63Value, name: row.nombre_medicion })),
      }))
      .filter((item) => new Set(item.points.map((point) => point.x)).size > 1);

    const coagulantByFlocculant = Array.from(byKey(validRows, (row) => `${row.planta} | F ${row.doseF}`))
      .map(([label, rows]) => ({
        label,
        points: rows.map((row) => ({ x: row.doseC, y: row.t63Value, name: row.nombre_medicion })),
      }))
      .filter((item) => item.points.length > 1);

    return { coagulantZeroFloc, flocculantFixedCoagulant, coagulantByFlocculant };
  }, [history]);

  const canSave =
    planta.trim() &&
    fecha &&
    preview.length > 0 &&
    preview.every((item) => {
      const value = Number(dfValues[item.summary.nombre_medicion]);
      return Number.isFinite(value) && value > 0;
    });

  async function refreshStatus() {
    try {
      await api("/health");
      setStatus("connected");
    } catch {
      setStatus("offline");
    }
  }

  async function refreshHistory(filters = {}) {
    const query = new URLSearchParams();
    if (filters.planta) query.set("planta", filters.planta);
    if (filters.fecha) query.set("fecha", filters.fecha);
    const rows = await api(`/history${query.toString() ? `?${query.toString()}` : ""}`);
    setHistory(rows);
  }

  async function refreshPlants() {
    const rows = await api("/plants");
    setPlants(rows);
  }

  useEffect(() => {
    refreshStatus();
    refreshHistory().catch(() => {});
    refreshPlants().catch(() => {});
  }, []);

  async function handlePreview(event) {
    event.preventDefault();
    if (!files.length) {
      setNotice({ type: "error", text: "Selecciona al menos un archivo CSV antes de procesar." });
      return;
    }

    setNotice(null);
    setBusy(true);
    try {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      form.append("clear_measurements", clearMeasurements ? "true" : "false");
      const result = await api("/analysis/preview", { method: "POST", body: form });
      setPreview(result.measurements || []);
      const nextDf = {};
      for (const item of result.measurements || []) {
        nextDf[item.summary.nombre_medicion] = formatNumber(item.summary.df_sugerido, 3);
      }
      setDfValues(nextDf);
      setNotice({
        type: result.errors?.length ? "error" : "success",
        text: result.errors?.length
          ? "La vista previa se generó, pero algunos archivos no se pudieron procesar."
          : "Vista previa generada. Revisa los Df antes de guardar.",
      });
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    if (!planta.trim()) {
      setNotice({ type: "error", text: "Escribe el nombre de la planta antes de guardar." });
      return;
    }
    if (!canSave) {
      setNotice({ type: "error", text: "Revisa que todas las mediciones tengan un Df válido mayor que cero." });
      return;
    }

    setNotice(null);
    setBusy(true);
    try {
      const payload = {
        planta: planta.trim(),
        fecha,
        replace_existing: false,
        mediciones: preview.map((item) => ({
          nombre_medicion: item.summary.nombre_medicion,
          df: Number(dfValues[item.summary.nombre_medicion]),
          series: item.series,
        })),
      };
      const result = await api("/analysis/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setNotice({ type: "success", text: `Guardadas ${result.saved} mediciones en el histórico.` });
      await refreshHistory({ planta: planta.trim(), fecha });
      await refreshPlants();
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function applyHistoryFilters() {
    setBusy(true);
    try {
      await refreshHistory({ planta: selectedPlant, fecha: selectedDate });
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function deleteRecord(row) {
    const confirmed = window.confirm(`Eliminar la medición "${row.nombre_medicion}" del ${row.fecha}?`);
    if (!confirmed) return;

    setBusy(true);
    try {
      await api(`/history/${row.id}`, { method: "DELETE" });
      await applyHistoryFilters();
      setNotice({ type: "success", text: "Registro eliminado." });
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function clearHistory() {
    if (!history.length) {
      setNotice({ type: "error", text: "No hay registros históricos para borrar." });
      return;
    }

    const confirmation = window.prompt(
      `Esta acción borrará ${history.length} registros históricos guardados. Escribe BORRAR para confirmar.`
    );
    if (confirmation !== "BORRAR") return;

    setBusy(true);
    try {
      const result = await api("/history", { method: "DELETE" });
      setHistory([]);
      setPlants([]);
      setSelectedPlant("");
      setSelectedDate("");
      setNotice({ type: "success", text: `Se borraron ${result.deleted} registros históricos.` });
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">F</div>
          <div>
            <strong>Floccam</strong>
            <span>Analyzer</span>
          </div>
        </div>

        <nav>
          <a href="#analysis">
            <FileUp size={18} /> Análisis
          </a>
          <a href="#history">
            <History size={18} /> Históricos
          </a>
          <a href="#comparisons">
            <FlaskConical size={18} /> Comparativos
          </a>
          <a href="#system">
            <Database size={18} /> Sistema
          </a>
        </nav>

        <section id="system" className="status-card">
          <span>Base de datos</span>
          <strong className={status === "connected" ? "ok" : "bad"}>
            {status === "checking" ? "Verificando" : status === "connected" ? "Conectada" : "Sin conexión"}
          </strong>
          <button className="ghost" onClick={refreshStatus} type="button">
            <RefreshCw size={16} /> Revisar
          </button>
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p>Panel operativo</p>
            <h1>Control de mediciones de floculación</h1>
          </div>
          <div className="api-pill">
            <Activity size={16} /> API activa
          </div>
        </header>

        <Notice notice={notice} />

        <section id="analysis" className="band">
          <div className="section-title">
            <div>
              <p>Nuevo análisis</p>
              <h2>Carga CSV y ajuste de Df</h2>
            </div>
            <div className="summary-strip">
              <Metric label="Mediciones" value={analysisTotals.measurements} />
              <Metric label="Puntos" value={analysisTotals.points} />
              <Metric label="T63 prom." value={formatNumber(analysisTotals.avgT63, 1)} unit="s" />
            </div>
          </div>

          <form className="analysis-form" onSubmit={handlePreview}>
            <label>
              Planta
              <input value={planta} onChange={(event) => setPlanta(event.target.value)} placeholder="Aguas_Frias" />
            </label>
            <label>
              Fecha
              <input type="date" value={fecha} onChange={(event) => setFecha(event.target.value)} />
            </label>
            <label className="file-input">
              Archivos CSV
              <span className="file-picker">
                <UploadCloud size={18} />
                {fileLabel(files)}
              </span>
              <input
                multiple
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => {
                  setFiles(Array.from(event.target.files || []));
                  setPreview([]);
                }}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={clearMeasurements}
                onChange={(event) => setClearMeasurements(event.target.checked)}
              />
              Limpiar mediciones temporales
            </label>
            <button disabled={busy || !files.length} type="submit">
              <LineChart size={18} /> {busy ? "Procesando..." : "Procesar"}
            </button>
          </form>

          <div className="preview-grid">
            {preview.map((item) => (
              <article className="measurement" key={item.summary.nombre_medicion}>
                <div className="measurement-head">
                  <div>
                    <p>Medición</p>
                    <h3>{item.summary.nombre_medicion}</h3>
                  </div>
                  <label>
                    Df final
                    <input
                      type="number"
                      min="0"
                      step="0.001"
                      value={dfValues[item.summary.nombre_medicion] || ""}
                      onChange={(event) =>
                        setDfValues((current) => ({
                          ...current,
                          [item.summary.nombre_medicion]: event.target.value,
                        }))
                      }
                    />
                  </label>
                </div>
                <MiniChart series={item.series} />
                <div className="metrics-row">
                  <Metric label="Di" value={formatNumber(item.summary.di)} unit="mm" />
                  <Metric label="Df sugerido" value={formatNumber(item.summary.df_sugerido)} unit="mm" />
                  <Metric label="T63 sugerido" value={formatNumber(item.summary.t63_sugerido, 1)} unit="s" />
                  <Metric label="Dosis C" value={formatNumber(item.summary.dosis_coagulante, 2)} />
                  <Metric label="Dosis F" value={formatNumber(item.summary.dosis_floculante, 2)} />
                </div>
              </article>
            ))}
          </div>

          {preview.length > 0 && (
            <div className="actions-row">
              <button disabled={busy || !canSave} onClick={handleSave} type="button">
                <Save size={18} /> Guardar histórico
              </button>
            </div>
          )}
        </section>

        <section id="history" className="band">
          <div className="section-title">
            <div>
              <p>Consulta</p>
              <h2>Históricos guardados</h2>
            </div>
            <div className="button-group">
              <button className="ghost" type="button" onClick={() => refreshHistory()}>
                <RefreshCw size={16} /> Actualizar
              </button>
              <button className="danger-soft" type="button" onClick={clearHistory} disabled={busy || !history.length}>
                <Trash2 size={16} /> Borrar histórico
              </button>
            </div>
          </div>

          <div className="filters">
            <label>
              Planta
              <select value={selectedPlant} onChange={(event) => setSelectedPlant(event.target.value)}>
                <option value="">Todas</option>
                {plants.map((plant) => (
                  <option value={plant} key={plant}>
                    {plant}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Fecha
              <input type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} />
            </label>
            <button type="button" onClick={applyHistoryFilters} disabled={busy}>
              Filtrar
            </button>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Planta</th>
                  <th>Medición</th>
                  <th>Dosis C</th>
                  <th>Dosis F</th>
                  <th>Di</th>
                  <th>Df</th>
                  <th>Delta D</th>
                  <th>T63</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr key={row.id}>
                    <td>{row.fecha}</td>
                    <td>{row.planta}</td>
                    <td className="strong-cell">{row.nombre_medicion}</td>
                    <td>{formatNumber(row.dosis_coagulante, 2)}</td>
                    <td>{formatNumber(row.dosis_floculante, 2)}</td>
                    <td>{formatNumber(row.di)}</td>
                    <td>{formatNumber(row.df)}</td>
                    <td>{formatNumber(row.delta_d)}</td>
                    <td>{formatNumber(row.t63, 1)}</td>
                    <td>
                      <button className="icon danger" type="button" onClick={() => deleteRecord(row)} aria-label="Eliminar registro">
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
                {!history.length && (
                  <tr>
                    <td colSpan="10" className="empty">
                      No hay registros para los filtros actuales.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section id="comparisons" className="band">
          <div className="section-title">
            <div>
              <p>Dosis y desempeño</p>
              <h2>Comparativos T63</h2>
            </div>
          </div>

          <div className="comparison-grid">
            <ComparisonChart
              title="Coagulante vs T63 con floculante en cero"
              xLabel="Dosis coagulante"
              series={comparisons.coagulantZeroFloc}
            />
            <ComparisonChart
              title="Floculante vs T63 con coagulante fijo"
              xLabel="Dosis floculante"
              series={comparisons.flocculantFixedCoagulant}
            />
            <ComparisonChart
              title="Coagulante vs T63 comparando floculante"
              xLabel="Dosis coagulante"
              series={comparisons.coagulantByFlocculant}
            />
          </div>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
