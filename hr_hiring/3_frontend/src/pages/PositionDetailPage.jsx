import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useParams } from "react-router-dom";
import {
  createCandidate,
  deleteCandidate,
  deletePositionDocument,
  getPositionDetail,
  listPositionCandidates,
  startEvaluation,
  uploadCandidateDocument,
  uploadPositionDocument,
} from "../api";
import { useAuth } from "../AuthContext";
import { useDarkMode } from "../hooks/useDarkMode";

const REC_LABEL = { DOPORUCIT: "Doporučit", ZVAZIT: "Zvážit", NEDOPORUCIT: "Nedoporučit" };
const REC_CLASS = { DOPORUCIT: "badge-active", ZVAZIT: "badge-warn", NEDOPORUCIT: "badge-archived" };

function parseJson(str) {
  if (!str) return null;
  try { return JSON.parse(str); } catch { return null; }
}

// ── Delete button ────────────────────────────────────────────────────────────
function DeleteBtn({ candidateId, onDeleted }) {
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleDelete(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirming) { setConfirming(true); return; }
    setLoading(true);
    try {
      await deleteCandidate(candidateId);
      onDeleted(candidateId);
    } catch {
      setConfirming(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      className={`cc-delete-btn ${confirming ? "cc-delete-btn--confirm" : ""}`}
      onClick={handleDelete}
      onBlur={() => setConfirming(false)}
      title={confirming ? "Klikněte znovu pro potvrzení" : "Smazat kandidáta"}
      disabled={loading}
    >
      {loading ? "…" : confirming ? "Smazat?" : "×"}
    </button>
  );
}

// ── Criterion bar (card style) ───────────────────────────────────────────────
function CriterionBar({ name, score, index }) {
  const pct = Math.round((score / 5) * 100);
  const color = score >= 4 ? "var(--good)" : score >= 3 ? "var(--warn)" : "var(--bad)";
  const dots = [1, 2, 3].map((d) => {
    const filled = score >= (d === 1 ? 4 : d === 2 ? 2.5 : 1);
    return filled;
  });
  return (
    <div className="cc-crit">
      <span className="cc-crit-idx">{index}.</span>
      <span className="cc-crit-name">{name.length > 22 ? name.slice(0, 20) + "…" : name}</span>
      <div className="cc-crit-track">
        <div className="cc-crit-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="cc-crit-dots">
        {dots.map((on, i) => (
          <span key={i} className={`cc-dot ${on ? "cc-dot--on" : ""}`} style={on ? { background: color } : {}} />
        ))}
      </div>
    </div>
  );
}

// ── Candidate card ───────────────────────────────────────────────────────────
function CandidateCard({ c, onDeleted }) {
  const card = parseJson(c.evaluation_json);
  const evalDone = c.evaluation_status === "completed" && card;
  const isExtracting = c.profile_status === "extracting";
  const isLoading = isExtracting || c.evaluation_status === "processing" || c.evaluation_status === "pending";
  const displayName = c.full_name && !c.full_name.startsWith("_") ? c.full_name : null;

  if (isLoading) {
    return (
      <div className="cand-card cand-card--loading">
        <DeleteBtn candidateId={c.candidate_id} onDeleted={onDeleted} />
        <div className="cc-spinner" />
        <div className="cc-loading-label">{isExtracting ? "Vytahuje se profil…" : "Hodnotí se…"}</div>
        {displayName && <div className="cc-loading-name">{displayName}</div>}
      </div>
    );
  }

  if (c.profile_status === "failed" || c.evaluation_status === "failed") {
    return (
      <div className="cand-card cand-card--error" style={{ position: "relative" }}>
        <DeleteBtn candidateId={c.candidate_id} onDeleted={onDeleted} />
        <div className="cc-name">{displayName || "Kandidát"}</div>
        <div style={{ fontSize: "11px", color: "var(--bad)", margin: "0.25rem 0" }}>Chyba při zpracování</div>
        <Link to={`/candidates/${c.candidate_id}`} style={{ fontSize: "12px", color: "var(--accent)" }}>
          Zobrazit detail →
        </Link>
      </div>
    );
  }

  const mustHave = card?.criteria?.filter(cr => cr.criterion_type === "must_have").slice(0, 4) || [];
  const skillTags = card?.skill_tags || [];

  const REC_BADGE_CLS = { DOPORUCIT: "cc-rec--best", ZVAZIT: "cc-rec--consider", NEDOPORUCIT: "cc-rec--no" };
  const REC_BADGE_LABEL = { DOPORUCIT: "Nejlepší shoda", ZVAZIT: "Zvážit", NEDOPORUCIT: "Nevhodný" };

  return (
    <Link to={`/candidates/${c.candidate_id}`} className="cand-card" style={{ textDecoration: "none", position: "relative" }}>
      <DeleteBtn candidateId={c.candidate_id} onDeleted={onDeleted} />

      {/* Header row */}
      <div className="cc-header">
        {evalDone && c.recommendation ? (
          <span className={`cc-rec-badge ${REC_BADGE_CLS[c.recommendation] || ""}`}>
            {REC_BADGE_LABEL[c.recommendation] || c.recommendation}
          </span>
        ) : <span />}
        {c.external_ref && <span className="cc-ref">TB: {c.external_ref}</span>}
        {!c.external_ref && c.overall_score != null && (
          <span className="cc-score">{c.overall_score.toFixed(1)}<span style={{ fontSize: "10px", fontWeight: 400 }}>/5</span></span>
        )}
      </div>

      {/* Name + role */}
      <div className="cc-name">{displayName || "—"}</div>
      {card?.current_role && <div className="cc-role">{card.current_role}</div>}

      {/* Must-have criteria bars */}
      {mustHave.length > 0 && (
        <div className="cc-crits">
          {mustHave.map((cr, i) => <CriterionBar key={i} name={cr.name} score={cr.score} index={i + 1} />)}
        </div>
      )}

      {/* Skill tags */}
      {skillTags.length > 0 && (
        <div className="cc-tags">
          {skillTags.map((t, i) => (
            <span key={i} className={`cc-tag cc-tag--${t.status || "neutral"}`}>
              {t.status === "match" ? `${t.label} ✓` : t.label}
            </span>
          ))}
        </div>
      )}

      {/* Rationale */}
      {card?.recommendation_rationale && (
        <div className="cc-rationale">{card.recommendation_rationale}</div>
      )}

      {/* Footer: salary + availability */}
      {(card?.salary_expectation || card?.availability) && (
        <div className="cc-footer">
          {card.salary_expectation && <span>{card.salary_expectation}</span>}
          {card.availability && <span>{card.availability}</span>}
        </div>
      )}

      {/* Stale warning */}
      {c.is_stale && evalDone && (
        <div className="cc-stale-badge">
          ⚠ Hodnocení je zastaralé
        </div>
      )}

      {!evalDone && !isLoading && (
        <div style={{ marginTop: "auto", fontSize: "11px", color: "var(--text-faint)", paddingTop: "0.5rem" }}>
          Hodnocení nebylo spuštěno
        </div>
      )}
    </Link>
  );
}

// ── Add Candidate Modal ──────────────────────────────────────────────────────
function AddCandidateModal({ positionId, onClose, onCreated }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const nameRef = useRef(null);

  useEffect(() => {
    nameRef.current?.focus();
    const prev = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    document.body.style.paddingRight = `${prev}px`;
    return () => {
      document.body.style.overflow = "";
      document.body.style.paddingRight = "";
    };
  }, []);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" && !loading) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, loading]);

  function addFiles(newFiles) {
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...newFiles.filter(f => !names.has(f.name))];
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (files.length === 0 && !fullName.trim()) { setError("Zadejte jméno nebo přiložte dokumenty."); return; }
    setLoading(true);
    setError("");
    try {
      setProgress("Zakládám kartu kandidáta…");
      const candidate = await createCandidate({
        position_id: positionId,
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim(),
        external_ref: externalRef.trim(),
      });

      for (let i = 0; i < files.length; i++) {
        setProgress(`Nahrávám dokument ${i + 1} / ${files.length}…`);
        await uploadCandidateDocument(candidate.candidate_id, {
          document_type: "cv",
          file: files[i],
          text_content: null,
        });
      }

      if (files.length > 0) {
        setProgress("Spouštím hodnocení…");
        await startEvaluation(candidate.candidate_id);
      }

      onCreated();
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || "Chyba při vytváření kandidáta.");
    } finally {
      setLoading(false);
      setProgress("");
    }
  }

  return createPortal(
    <div
      className="modal-overlay"
      onClick={(e) => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className="modal" style={{ maxWidth: "580px", height: "auto", maxHeight: "90vh" }}>
        <div className="modal-header">
          <h2>Nový kandidát</h2>
          <button className="modal-close" onClick={onClose} disabled={loading}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="error-banner">{error}</div>}

            <div className="field-row">
              <div className="field" style={{ flex: 2 }}>
                <label className="field-label">Jméno a příjmení</label>
                <input
                  ref={nameRef}
                  className="field-input"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Ing. Jan Novák"
                  maxLength={250}
                  disabled={loading}
                />
              </div>
              <div className="field" style={{ flex: 2 }}>
                <label className="field-label">E-mail</label>
                <input
                  className="field-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="jan@firma.cz"
                  disabled={loading}
                />
              </div>
            </div>

            <div className="field-row">
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Telefon</label>
                <input
                  className="field-input"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+420 …"
                  maxLength={64}
                  disabled={loading}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Ref. č.</label>
                <input
                  className="field-input"
                  value={externalRef}
                  onChange={(e) => setExternalRef(e.target.value)}
                  placeholder="CV-001"
                  maxLength={200}
                  disabled={loading}
                />
              </div>
            </div>

            <div className="field">
              <label className="field-label">Dokumenty kandidáta</label>
              <div
                className={`dropzone ${isDragging ? "dropzone-active" : ""}`}
                style={{ minHeight: "90px", cursor: loading ? "default" : "pointer" }}
                onDragOver={(e) => { e.preventDefault(); if (!loading) setIsDragging(true); }}
                onDragEnter={(e) => { e.preventDefault(); if (!loading) setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (!loading) addFiles(Array.from(e.dataTransfer.files));
                }}
                onClick={() => !loading && inputRef.current?.click()}
              >
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.txt,.rtf"
                  style={{ display: "none" }}
                  onChange={(e) => {
                    addFiles(Array.from(e.target.files || []));
                    e.target.value = "";
                  }}
                />
                {files.length === 0 ? (
                  <>
                    <span className="dropzone-icon">📎</span>
                    <p className="dropzone-label">Přetáhněte dokumenty nebo <span className="dropzone-link">vyberte kliknutím</span></p>
                    <p className="dropzone-hint">CV, přepis pohovoru, hodnocení · PDF, DOCX, TXT · nepovinné</p>
                  </>
                ) : (
                  <div className="file-list" onClick={(e) => e.stopPropagation()}>
                    {files.map((f, i) => (
                      <div key={i} className="file-pill">
                        <span>📄 {f.name}</span>
                        {!loading && (
                          <button
                            type="button"
                            className="file-pill-remove"
                            onClick={() => setFiles(prev => prev.filter((_, j) => j !== i))}
                          >×</button>
                        )}
                      </div>
                    ))}
                    {!loading && (
                      <button
                        type="button"
                        className="btn-ghost"
                        style={{ fontSize: "12px", padding: "0.2rem 0.6rem", marginTop: "0.25rem" }}
                        onClick={() => inputRef.current?.click()}
                      >
                        + přidat další
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {progress && (
              <div style={{ fontSize: "12px", color: "var(--text-muted)", display: "flex", gap: "0.4rem", alignItems: "center" }}>
                <div className="cc-spinner" style={{ width: "14px", height: "14px", borderWidth: "2px" }} />
                {progress}
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button type="button" className="btn-ghost" onClick={onClose} disabled={loading}>Zrušit</button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? "⟳ Ukládám…" : "Vytvořit kandidáta"}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}

// ── Position documents panel ─────────────────────────────────────────────────
const DOC_TYPE_LABEL = { job_description: "Job Description", supplementary: "Doplňkový dok." };

function PositionDocuments({ positionId, documents, onChanged }) {
  const [docType, setDocType] = useState("job_description");
  const [docFile, setDocFile] = useState(null);
  const [docText, setDocText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const fileRef = useRef(null);

  async function handleUpload(e) {
    e.preventDefault();
    if (!docFile && !docText.trim()) { setMsg("Vyberte soubor nebo zadejte text."); return; }
    setUploading(true); setMsg("");
    try {
      await uploadPositionDocument(positionId, { document_type: docType, file: docFile, text_content: docText });
      setDocFile(null); setDocText("");
      if (fileRef.current) fileRef.current.value = "";
      setMsg("✓ Nahráno");
      setExpanded(false);
      onChanged();
    } catch { setMsg("Chyba při nahrávání."); }
    finally { setUploading(false); }
  }

  async function handleDelete(documentId) {
    setDeletingId(documentId);
    try { await deletePositionDocument(positionId, documentId); onChanged(); }
    catch { /* ignore */ }
    finally { setDeletingId(null); }
  }

  return (
    <div className="pd-docs-panel">
      <div className="pd-docs-header">
        <span className="db-priority-label">PODKLADY POZICE</span>
        <button className="ghost-link" style={{ fontSize: "12px" }} onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Zavřít" : "+ Přidat dokument"}
        </button>
      </div>

      {documents.length === 0 && !expanded ? (
        <span className="pd-docs-empty">Žádné dokumenty — klikněte na „Přidat dokument"</span>
      ) : (
        <div className="pd-docs-list">
          {documents.map((doc) => (
            <div key={doc.document_id} className="pd-doc-row">
              <span className="pd-doc-icon">📄</span>
              <span className="pd-doc-name">{doc.file_name}</span>
              <span className={`rec-badge ${doc.document_type === "job_description" ? "rec-badge--best" : "rec-badge--consider"}`} style={{ fontSize: "10px", padding: "0.1rem 0.5rem" }}>
                {DOC_TYPE_LABEL[doc.document_type] || doc.document_type}
              </span>
              <button className="pd-doc-del" onClick={() => handleDelete(doc.document_id)} disabled={deletingId === doc.document_id}>
                {deletingId === doc.document_id ? "…" : "×"}
              </button>
            </div>
          ))}
        </div>
      )}

      {expanded && (
        <form onSubmit={handleUpload} className="pd-docs-form">
          <select className="filter-select" style={{ fontSize: "12px" }} value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="job_description">Job Description</option>
            <option value="supplementary">Doplňkový</option>
          </select>
          <input ref={fileRef} type="file" className="field-input" style={{ fontSize: "12px", flex: 1 }}
            onChange={(e) => setDocFile(e.target.files?.[0] || null)} />
          <input className="field-input" placeholder="nebo vložte text…" value={docText} style={{ fontSize: "12px", flex: 2 }}
            onChange={(e) => setDocText(e.target.value)} />
          <button type="submit" className="btn-primary" style={{ fontSize: "12px", padding: "0.35rem 0.8rem", whiteSpace: "nowrap" }} disabled={uploading}>
            {uploading ? "⟳" : "Nahrát"}
          </button>
          {msg && <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>{msg}</span>}
        </form>
      )}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────
export function PositionDetailPage() {
  const { positionId } = useParams();
  const { theme, toggle } = useDarkMode();
  const { canAddCandidate } = useAuth();
  const [position, setPosition] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const pollingRef = useRef(null);

  async function loadPosition() {
    const data = await getPositionDetail(positionId);
    setPosition(data);
    return data;
  }

  async function loadCandidates() {
    const data = await listPositionCandidates(positionId);
    const items = data.items || [];
    setCandidates(items);
    return items;
  }

  function needsPolling(items) {
    return items.some(
      (c) => c.profile_status === "extracting" || c.evaluation_status === "processing" || c.evaluation_status === "pending"
    );
  }

  function startPolling() {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      const items = await loadCandidates();
      if (!needsPolling(items)) stopPolling();
    }, 3000);
  }

  function stopPolling() {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
  }

  useEffect(() => {
    loadPosition();
    loadCandidates().then((items) => { if (needsPolling(items)) startPolling(); });
    return stopPolling;
  }, [positionId]);

  function handleCreated() {
    loadCandidates().then((items) => { if (needsPolling(items)) startPolling(); });
  }

  function fmtSalary(pos) {
    if (!pos?.salary_from && !pos?.salary_to) return null;
    const fmt = (n) => n ? `${Math.round(n).toLocaleString("cs-CZ")} Kč` : "";
    if (pos.salary_from && pos.salary_to) return `${fmt(pos.salary_from)} – ${fmt(pos.salary_to)}`;
    return fmt(pos.salary_from || pos.salary_to);
  }

  const evalDone = candidates.filter((c) => c.evaluation_status === "completed").length;
  const pending = candidates.filter((c) => !c.evaluation_status || c.evaluation_status === "pending" || c.evaluation_status === "processing" || c.profile_status === "extracting").length;

  // Build metadata items for the PRIORITA-style row
  const metaItems = [];
  if (position) {
    if (fmtSalary(position)) metaItems.push({ label: "MZDOVÉ ROZMEZÍ", value: fmtSalary(position) });
    if (position.opened_at) metaItems.push({ label: "VYPSÁNO", value: new Date(position.opened_at).toLocaleDateString("cs-CZ") });
    metaItems.push({ label: "STAV", value: position.status === "active" ? "Aktivní" : "Archivováno" });
    if (position.description) metaItems.push({ label: "POPIS", value: position.description.length > 60 ? position.description.slice(0, 58) + "…" : position.description });
  }

  return (
    <div className="db-page">
      {/* Dark header */}
      <header className="db-header">
        <div className="db-header-inner">
          <div className="db-header-top">
            <div>
              <div className="db-header-eyebrow">VÝBĚROVÉ ŘÍZENÍ · {new Date().getFullYear()}</div>
              <h1 className="db-header-title">{position?.title || "…"}</h1>
            </div>
            <div className="db-header-nav">
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end", marginBottom: "0.5rem" }}>
                <span className="ghost-link" style={{ color: "#e6edf3", borderColor: "#444c56", cursor: "default" }}>
                  {candidates.length} kandidátů
                </span>
                {evalDone > 0 && (
                  <span className="ghost-link" style={{ color: "#3fb950", borderColor: "#3fb950", cursor: "default" }}>
                    {evalDone} hodnocených
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                <Link to="/" className="ghost-link" style={{ color: "#e6edf3", borderColor: "#444c56" }}>← Pozice</Link>
                <button className="theme-toggle" onClick={toggle} style={{ borderColor: "#444c56", color: "#e6edf3" }}>
                  {theme === "dark" ? "☀︎" : "☽"}
                </button>
              </div>
            </div>
          </div>

          {metaItems.length > 0 && (
            <div className="db-priorities">
              {metaItems.map((m, i) => (
                <div key={i} className="db-priority-item">
                  <span className="db-priority-label">{m.label}</span>
                  <span className="db-priority-name">{m.value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* Body */}
      <div className="db-body">
        {/* Documents */}
        {position && (
          <PositionDocuments
            positionId={positionId}
            documents={position.documents || []}
            onChanged={loadPosition}
          />
        )}

        {/* Position-level staleness banner */}
        {candidates.some((c) => c.is_stale && c.stale_reason === "position_docs_changed") && (
          <div className="stale-banner">
            <span className="stale-banner-icon">⚠</span>
            <span>Změnil se popis pozice — je třeba přehodnotit kandidáty s zastaralým hodnocením.</span>
          </div>
        )}

        {/* Candidates header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <div>
            <div className="db-priority-label">KANDIDÁTI</div>
            <div style={{ fontSize: "22px", fontWeight: 700 }}>{candidates.length > 0 ? candidates.length : "—"}</div>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            {evalDone > 0 && (
              <Link to={`/positions/${positionId}/dashboard`} className="ghost-link" style={{ fontSize: "13px", textDecoration: "none" }}>
                Dashboard →
              </Link>
            )}
            {canAddCandidate && (
              <button className="btn-primary" onClick={() => setShowModal(true)}>
                + Přidat kandidáta
              </button>
            )}
          </div>
        </div>

        {candidates.length === 0 ? (
          <div className="card" style={{ padding: "3rem", textAlign: "center", color: "var(--text-faint)" }}>
            Žádní kandidáti — klikněte na „Přidat kandidáta"
          </div>
        ) : (
          <div className="cand-grid">
            {candidates.map((c) => (
              <CandidateCard
                key={c.candidate_id}
                c={c}
                onDeleted={(id) => setCandidates((prev) => prev.filter((x) => x.candidate_id !== id))}
              />
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <AddCandidateModal
          positionId={positionId}
          onClose={() => setShowModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}
