import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listCards, uploadCard } from "../api";
import { DropZone } from "../components/DropZone";
import { Shell } from "../components/Shell";

const STATUS_LABELS = {
  processing: "Zpracovávám",
  ready: "Připraveno",
  exported: "Exportováno",
  error: "Chyba",
};

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status] || status}</span>;
}

const SORT_COLS = [
  { key: "created_at", label: "Nahráno" },
  { key: "date", label: "Datum výroby" },
  { key: "status", label: "Stav" },
];

export function CardsListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState("desc");
  const [filters, setFilters] = useState({ search: "", status: "", line_number: "", operator: "" });
  const pollRef = useRef(null);

  const PAGE_SIZE = 20;

  async function load() {
    setLoading(true);
    try {
      const params = {
        page, page_size: PAGE_SIZE,
        sort_by: sortBy, sort_dir: sortDir,
        ...(filters.search && { search: filters.search }),
        ...(filters.status && { status: filters.status }),
        ...(filters.line_number && { line_number: filters.line_number }),
        ...(filters.operator && { operator: filters.operator }),
      };
      const d = await listCards(params);
      setData(d);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [page, sortBy, sortDir, filters]);

  // Auto-refresh if any card is processing
  useEffect(() => {
    const hasProcessing = data?.items?.some((c) => c.status === "processing");
    if (hasProcessing) {
      pollRef.current = setTimeout(load, 3000);
    }
    return () => clearTimeout(pollRef.current);
  }, [data]);

  async function handleFile(file) {
    setUploading(true);
    setUploadError(null);
    try {
      const res = await uploadCard(file);
      navigate(`/cards/${res.card_id}`);
    } catch (e) {
      setUploadError("Nahrání selhalo: " + (e.response?.data?.detail || e.message));
      setUploading(false);
    }
  }

  function toggleSort(col) {
    if (sortBy === col) setSortDir((d) => d === "desc" ? "asc" : "desc");
    else { setSortBy(col); setSortDir("desc"); }
    setPage(1);
  }

  function setFilter(key, value) {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  return (
    <Shell>
      <div className="flex justify-between flex-center mb-4">
        <h1 style={{ fontSize: "1.4rem", fontWeight: 600 }}>Výrobní karty</h1>
        <span className="text-dim text-sm">{data ? `${data.total} karet celkem` : ""}</span>
      </div>

      {/* Upload */}
      <div className="card mb-4">
        <div className="section-heading">Nová karta — nahrát PDF</div>
        {uploading ? (
          <div className="processing-state">
            <div className="spinner" />
            <span>Nahrávám a spouštím extrakci…</span>
          </div>
        ) : (
          <>
            <DropZone onFile={handleFile} />
            {uploadError && <div style={{ color: "var(--danger)", marginTop: "0.5rem", fontSize: 13 }}>{uploadError}</div>}
          </>
        )}
      </div>

      {/* Filters */}
      <div className="filters">
        <input
          className="filter-input"
          placeholder="Hledat… (soubor, linka, nástroj, obsluha)"
          value={filters.search}
          onChange={(e) => setFilter("search", e.target.value)}
          style={{ flex: "1 1 160px" }}
        />
        <select className="filter-input" value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
          <option value="">Všechny stavy</option>
          <option value="processing">Zpracovávám</option>
          <option value="ready">Připraveno</option>
          <option value="exported">Exportováno</option>
          <option value="error">Chyba</option>
        </select>
        <input
          className="filter-input"
          placeholder="Číslo linky"
          value={filters.line_number}
          onChange={(e) => setFilter("line_number", e.target.value)}
          style={{ width: 130 }}
        />
        <input
          className="filter-input"
          placeholder="Obsluha"
          value={filters.operator}
          onChange={(e) => setFilter("operator", e.target.value)}
          style={{ width: 130 }}
        />
      </div>

      {/* Table */}
      <div className="card">
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
            <div className="spinner" />
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {SORT_COLS.map(({ key, label }) => (
                    <th key={key} onClick={() => toggleSort(key)}>
                      {label} {sortBy === key ? (sortDir === "desc" ? "↓" : "↑") : ""}
                    </th>
                  ))}
                  <th>Soubor</th>
                  <th>Linka</th>
                  <th>Nástroj</th>
                  <th>Rozměr</th>
                  <th>Obsluha</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.length === 0 && (
                  <tr>
                    <td colSpan={9} style={{ textAlign: "center", color: "var(--text-dim)", padding: "2rem" }}>
                      Žádné karty nenalezeny.
                    </td>
                  </tr>
                )}
                {data?.items?.map((card) => (
                  <tr key={card.card_id} className="clickable" onClick={() => navigate(`/cards/${card.card_id}`)}>
                    <td>
                      <span className="text-dim text-sm">
                        {new Date(card.created_at).toLocaleDateString("cs-CZ")}
                      </span>
                    </td>
                    <td>{card.date || <span className="text-dim">—</span>}</td>
                    <td><StatusBadge status={card.status} /></td>
                    <td className="text-sm font-mono" style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {card.original_filename}
                    </td>
                    <td>{card.line_number || <span className="text-dim">—</span>}</td>
                    <td>{card.tool || <span className="text-dim">—</span>}</td>
                    <td>{card.produced_dimension || <span className="text-dim">—</span>}</td>
                    <td>{card.operator || <span className="text-dim">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="pagination">
            <button className="btn btn-secondary btn-sm" onClick={() => setPage(1)} disabled={page === 1}>«</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setPage((p) => p - 1)} disabled={page === 1}>‹</button>
            <span className="text-dim text-sm">{page} / {totalPages}</span>
            <button className="btn btn-secondary btn-sm" onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages}>›</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setPage(totalPages)} disabled={page >= totalPages}>»</button>
          </div>
        )}
      </div>
    </Shell>
  );
}
