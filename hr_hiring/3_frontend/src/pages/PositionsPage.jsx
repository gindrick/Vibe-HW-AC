import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AddPositionModal } from "../components/AddPositionModal";
import { Shell } from "../components/Shell";
import { archivePosition, createPosition, fetchMe, listPositions, uploadPositionDocument } from "../api";

/* ── helpers ────────────────────────────────────────────────── */

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("cs-CZ", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function SortIcon({ col }) {
  const sorted = col.getIsSorted();
  if (!sorted) return <span className="sort-icon sort-none">↕</span>;
  return <span className="sort-icon">{sorted === "asc" ? "↑" : "↓"}</span>;
}

function StatusBadge({ status }) {
  return <span className={`status-badge badge-${status}`}>{status === "active" ? "Aktivní" : "Archiv"}</span>;
}

function SalaryCell({ salaryFrom, salaryTo, visible }) {
  const fmt = (v) => new Intl.NumberFormat("cs-CZ").format(v);
  if (salaryFrom == null && salaryTo == null) return <span className="cell-muted">—</span>;
  const range = salaryFrom != null && salaryTo != null
    ? `${fmt(salaryFrom)} – ${fmt(salaryTo)} Kč`
    : salaryFrom != null
    ? `od ${fmt(salaryFrom)} Kč`
    : `do ${fmt(salaryTo)} Kč`;
  return (
    <span className="salary-cell">
      <span>{range}</span>
      <span
        className={`vis-badge ${visible ? "vis-on" : "vis-off"}`}
        title={visible ? "Rozsah a požadavek uchazeče zahrnuty ve vyhodnocení" : "Nezahrnuto ve vyhodnocení"}
      >
        {visible ? "👁" : "🔒"}
      </span>
    </span>
  );
}

function DocsPills({ docs }) {
  if (!docs?.length) return <span className="cell-muted">—</span>;
  const shown = docs.slice(0, 3);
  const rest = docs.length - shown.length;
  return (
    <div className="doc-pills-cell">
      {shown.map((d) => (
        <span key={d.document_id} className={`doc-pill-sm ${d.is_text ? "pill-text" : "pill-file"}`} title={d.file_name}>
          {d.is_text ? "✏ Text" : `📄 ${d.file_name.length > 20 ? d.file_name.slice(0, 18) + "…" : d.file_name}`}
        </span>
      ))}
      {rest > 0 && <span className="doc-pill-sm pill-more">+{rest}</span>}
    </div>
  );
}

/* ── page ───────────────────────────────────────────────────── */

export function PositionsPage() {
  const [positions, setPositions] = useState([]);
  const [statusFilter, setStatusFilter] = useState("active");
  const [globalFilter, setGlobalFilter] = useState("");
  const [sorting, setSorting] = useState([{ id: "opened_at", desc: true }]);
  const [me, setMe] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [meData, posData] = await Promise.all([fetchMe(), listPositions(statusFilter)]);
      setMe(meData.user);
      setPositions(posData.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Nepodařilo se načíst data");
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  /* ── table columns ── */
  const columns = useMemo(
    () => [
      {
        accessorKey: "title",
        header: "Název pozice",
        cell: ({ row }) => (
          <Link to={`/positions/${row.original.position_id}`} className="pos-link">
            {row.original.title}
          </Link>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => <StatusBadge status={getValue()} />,
      },
      {
        accessorKey: "opened_at",
        header: "Datum zadání",
        cell: ({ getValue, row }) => formatDate(getValue() || row.original.created_at),
        sortingFn: "datetime",
      },
      {
        accessorKey: "salary",
        header: "Plat",
        cell: ({ row }) => <SalaryCell salaryFrom={row.original.salary_from} salaryTo={row.original.salary_to} visible={row.original.salary_visible} />,
      },
      {
        id: "documents",
        header: "Přílohy",
        cell: ({ row }) => <DocsPills docs={row.original.documents} />,
        enableSorting: false,
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) =>
          row.original.status !== "archived" ? (
            <button
              className="btn-outline-sm"
              onClick={async () => {
                await archivePosition(row.original.position_id);
                await load();
              }}
            >
              Archivovat
            </button>
          ) : null,
        enableSorting: false,
      },
    ],
    [load]
  );

  const table = useReactTable({
    data: positions,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  /* ── modal submit ── */
  async function handleAddPosition({ title, description, openedAt, salaryFrom, salaryTo, salaryVisible, files, textContent }) {
    setModalLoading(true);
    setError("");
    try {
      const position = await createPosition({
        title,
        description,
        opened_at: new Date(openedAt).toISOString(),
        salary_from: salaryFrom || null,
        salary_to: salaryTo || null,
        salary_visible: salaryVisible,
      });
      for (const file of files) {
        await uploadPositionDocument(position.position_id, { document_type: "job_description", file });
      }
      if (files.length === 0 && textContent.trim()) {
        await uploadPositionDocument(position.position_id, {
          document_type: "job_description",
          text_content: textContent,
        });
      }
      setShowModal(false);
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Nepodařilo se vytvořit pozici");
    } finally {
      setModalLoading(false);
    }
  }

  const rows = table.getRowModel().rows;

  return (
    <Shell title="HR Candidate Evaluation" subtitle="Správa pracovních pozic a hodnocení kandidátů">
      <div className="card">
        {/* Toolbar */}
        <div className="table-toolbar">
          <div className="toolbar-left">
            <div className="search-wrap">
              <span className="search-icon">⌕</span>
              <input
                className="search-input"
                placeholder="Hledat pozice…"
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
              />
              {globalFilter && (
                <button className="search-clear" onClick={() => setGlobalFilter("")} aria-label="Smazat hledání">
                  ×
                </button>
              )}
            </div>
            <select
              className="filter-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="active">Aktivní</option>
              <option value="archived">Archivované</option>
              <option value="all">Vše</option>
            </select>
          </div>
          <div className="toolbar-right">
            {me && (
              <div className="user-chip">
                <span className="user-chip-dot" />
                <span>
                  {me.display_name} · <em>{me.role}</em>
                </span>
              </div>
            )}
            <button className="btn-primary" onClick={() => setShowModal(true)}>
              + Přidat pozici
            </button>
          </div>
        </div>

        {error && <p className="error-banner">{error}</p>}

        {/* Table */}
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => (
                    <th
                      key={header.id}
                      className={header.column.getCanSort() ? "th-sortable" : ""}
                      onClick={header.column.getToggleSortingHandler()}
                      style={{ width: header.column.columnDef.size }}
                    >
                      <span className="th-inner">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() && <SortIcon col={header.column} />}
                      </span>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="empty-row">
                    {globalFilter ? "Žádné výsledky pro hledaný výraz" : "Žádné pozice nenalezeny"}
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id} className="data-row">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="table-footer-bar">
          <span className="table-count">
            {rows.length} {rows.length === 1 ? "pozice" : rows.length < 5 ? "pozice" : "pozic"}
            {globalFilter && ` (filtrováno z ${positions.length})`}
          </span>
        </div>
      </div>

      {showModal && (
        <AddPositionModal onClose={() => setShowModal(false)} onSubmit={handleAddPosition} loading={modalLoading} />
      )}
    </Shell>
  );
}
