import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  deleteCandidateDocument,
  getCandidate,
  getEvaluation,
  listCandidateDocuments,
  startEvaluation,
  updateCandidate,
  uploadCandidateDocument,
} from "../api";
import { useDarkMode } from "../hooks/useDarkMode";

const REC_LABEL = { DOPORUCIT: "Doporučit", ZVAZIT: "Zvážit", NEDOPORUCIT: "Nedoporučit" };
const REC_CLS   = { DOPORUCIT: "rec-badge--best", ZVAZIT: "rec-badge--consider", NEDOPORUCIT: "rec-badge--no" };
const DOC_TYPE_LABEL = { cv: "CV", interview_transcript: "Přepis pohovoru", other: "Ostatní" };

// ── Criterion bar ─────────────────────────────────────────────────────────────
function CriterionBar({ c }) {
  const pct = Math.round(((c.score || 0) / 5) * 100);
  const color = c.score >= 4 ? "var(--good)" : c.score >= 3 ? "var(--warn)" : "var(--bad)";
  return (
    <div className="crit-row">
      <div className="crit-row-head">
        <span className={`crit-type-pill ${c.criterion_type === "must_have" ? "crit-must" : "crit-nice"}`}>
          {c.criterion_type === "must_have" ? "Must" : "Nice"}
        </span>
        <span className="crit-name">{c.name}</span>
        <span className="crit-score" style={{ color }}>{c.score}/5</span>
      </div>
      <div className="crit-bar-track">
        <div className="crit-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      {c.evidence && <p className="crit-evidence">{c.evidence}</p>}
    </div>
  );
}

function Section({ title, items, color }) {
  if (!items?.length) return null;
  return (
    <div className="eval-section">
      <div className="eval-section-title" style={{ color }}>{title}</div>
      <ul className="eval-list">{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
    </div>
  );
}

// ── Editable info panel ───────────────────────────────────────────────────────
function InfoPanel({ candidate, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  function startEdit() {
    setForm({
      full_name: candidate.full_name?.startsWith("_") ? "" : (candidate.full_name || ""),
      email: candidate.email || "",
      phone: candidate.phone || "",
      external_ref: candidate.external_ref || "",
      notes: candidate.notes || "",
    });
    setMsg(""); setEditing(true);
  }

  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

  async function handleSave(e) {
    e.preventDefault();
    if (!form.full_name?.trim()) { setMsg("Jméno je povinné."); return; }
    if (!form.email?.trim()) { setMsg("E-mail je povinný."); return; }
    setSaving(true); setMsg("");
    try {
      const updated = await updateCandidate(candidate.candidate_id, form);
      onSaved(updated);
      setEditing(false);
    } catch { setMsg("Chyba při ukládání."); }
    finally { setSaving(false); }
  }

  const isPlaceholder = !candidate.full_name || candidate.full_name.startsWith("_");

  if (!editing) {
    return (
      <div className="pd-docs-panel" style={{ marginBottom: "1.25rem" }}>
        <div className="pd-docs-header">
          <span className="db-priority-label">INFORMACE O KANDIDÁTOVI</span>
          <button className="ghost-link" style={{ fontSize: "12px" }} onClick={startEdit}>Upravit</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem 1.5rem", paddingTop: "0.5rem" }}>
          <MetaField label="Jméno" value={isPlaceholder ? null : candidate.full_name} placeholder="Nevyplněno" />
          <MetaField label="E-mail" value={candidate.email} placeholder="Nevyplněno" />
          <MetaField label="Telefon" value={candidate.phone} placeholder="—" />
          <MetaField label="Ref. č." value={candidate.external_ref} placeholder="—" />
          {candidate.notes && (
            <div style={{ gridColumn: "1 / -1" }}>
              <MetaField label="Poznámky" value={candidate.notes} />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="pd-docs-panel" style={{ marginBottom: "1.25rem" }}>
      <div className="pd-docs-header">
        <span className="db-priority-label">UPRAVIT INFORMACE</span>
      </div>
      <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "0.75rem", paddingTop: "0.5rem" }}>
        {msg && <div className="error-banner">{msg}</div>}
        <div className="field-row">
          <div className="field" style={{ flex: 2 }}>
            <label className="field-label">Jméno a příjmení *</label>
            <input className="field-input" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} maxLength={250} disabled={saving} />
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label className="field-label">E-mail *</label>
            <input className="field-input" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} disabled={saving} />
          </div>
        </div>
        <div className="field-row">
          <div className="field" style={{ flex: 1 }}>
            <label className="field-label">Telefon</label>
            <input className="field-input" value={form.phone} onChange={(e) => set("phone", e.target.value)} maxLength={64} disabled={saving} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label className="field-label">Ref. č.</label>
            <input className="field-input" value={form.external_ref} onChange={(e) => set("external_ref", e.target.value)} maxLength={200} disabled={saving} />
          </div>
        </div>
        <div className="field">
          <label className="field-label">Poznámky</label>
          <textarea className="field-textarea" rows={3} value={form.notes} onChange={(e) => set("notes", e.target.value)} disabled={saving} />
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button type="submit" className="btn-primary" disabled={saving}>{saving ? "⟳ Ukládám…" : "Uložit"}</button>
          <button type="button" className="ghost-link" onClick={() => setEditing(false)} disabled={saving}>Zrušit</button>
        </div>
      </form>
    </div>
  );
}

function MetaField({ label, value, placeholder }) {
  return (
    <div>
      <div className="db-priority-label" style={{ marginBottom: "3px" }}>{label}</div>
      <div style={{ fontSize: "13.5px", color: value ? "var(--text)" : "var(--text-faint)" }}>{value || placeholder || null}</div>
    </div>
  );
}

// ── Documents panel ───────────────────────────────────────────────────────────
function DocumentsPanel({ candidateId, documents, onChanged }) {
  const [docType, setDocType] = useState("cv");
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
      await uploadCandidateDocument(candidateId, { document_type: docType, file: docFile, text_content: docText });
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
    try { await deleteCandidateDocument(candidateId, documentId); onChanged(); }
    catch { /* ignore */ }
    finally { setDeletingId(null); }
  }

  return (
    <div className="pd-docs-panel" style={{ marginBottom: "1.25rem" }}>
      <div className="pd-docs-header">
        <span className="db-priority-label">DOKUMENTY KANDIDÁTA</span>
        <button className="ghost-link" style={{ fontSize: "12px" }} onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Zavřít" : "+ Přidat dokument"}
        </button>
      </div>

      {documents.length === 0 && !expanded ? (
        <span className="pd-docs-empty">Žádné dokumenty — přidejte CV nebo přepis pohovoru.</span>
      ) : (
        <div className="pd-docs-list">
          {documents.map((doc) => (
            <div key={doc.document_id} className="pd-doc-row">
              <span className="pd-doc-icon">📄</span>
              <span className="pd-doc-name">{doc.file_name}</span>
              <span className={`rec-badge ${doc.document_type === "cv" ? "rec-badge--best" : "rec-badge--consider"}`} style={{ fontSize: "10px", padding: "0.1rem 0.5rem" }}>
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
            <option value="cv">CV</option>
            <option value="interview_transcript">Přepis pohovoru</option>
            <option value="other">Ostatní</option>
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

// ── Main page ─────────────────────────────────────────────────────────────────
export function CandidateDetailPage() {
  const { candidateId } = useParams();
  const { theme, toggle } = useDarkMode();
  const [candidate, setCandidate] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [evaluation, setEvaluation] = useState(null);
  const [evalStatus, setEvalStatus] = useState("idle");
  const [evaluating, setEvaluating] = useState(false);

  async function loadCandidate() {
    const data = await getCandidate(candidateId);
    setCandidate(data);
    return data;
  }

  async function loadDocuments() {
    const data = await listCandidateDocuments(candidateId);
    setDocuments(data || []);
    return data || [];
  }

  async function pollEvaluation() {
    try {
      const result = await getEvaluation(candidateId);
      setEvaluation(result);
      setEvalStatus(result.status || "idle");
      return result;
    } catch { return null; }
  }

  useEffect(() => {
    loadCandidate();
    loadDocuments();
    let active = true;
    let timer = null;
    async function tick() {
      const res = await pollEvaluation();
      if (!active || !res) return;
      if (res.status === "pending" || res.status === "processing") {
        timer = setTimeout(tick, 3000);
      }
    }
    tick();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [candidateId]);

  async function handleStartEval() {
    // Guard: if evaluation is current (not stale), ask for confirmation
    if (evaluation?.status === "completed" && !evaluation?.is_stale) {
      const ok = window.confirm(
        "Hodnocení je aktuální a žádné dokumenty se nezměnily.\nPřesto spustit znovu? Bude zaúčtováno volání LLM."
      );
      if (!ok) return;
    }

    setEvaluating(true);
    try {
      await startEvaluation(candidateId);
      setEvalStatus("pending");
      let res = null;
      while (!res || res.status === "pending" || res.status === "processing") {
        await new Promise((r) => setTimeout(r, 3000));
        res = await pollEvaluation();
        if (!res) break;
      }
    } finally {
      setEvaluating(false);
      loadCandidate(); // refresh name/email if extractor updated them
    }
  }

  const card = evaluation?.card;
  const rec = card?.recommendation || evaluation?.recommendation;
  const positionId = candidate?.position_id;
  const isPlaceholder = !candidate?.full_name || candidate?.full_name?.startsWith("_");
  const hasName = candidate && !isPlaceholder && candidate.full_name.trim();
  const hasEmail = candidate?.email?.trim();
  const hasDocs = documents.length > 0;
  const canEvaluate = hasName && hasEmail && hasDocs && evalStatus !== "processing" && !evaluating;

  const mustHave = useMemo(() => card?.criteria?.filter((c) => c.criterion_type === "must_have") || [], [card]);
  const niceHave = useMemo(() => card?.criteria?.filter((c) => c.criterion_type === "nice_to_have") || [], [card]);

  // Build meta items for the PRIORITA-style header row
  const profile = (() => { try { return JSON.parse(candidate?.profile_json || "{}"); } catch { return {}; } })();
  const metaItems = [];
  if (candidate?.email) metaItems.push({ label: "E-MAIL", value: candidate.email });
  if (candidate?.phone) metaItems.push({ label: "TELEFON", value: candidate.phone });
  if (profile.current_role) metaItems.push({ label: "POZICE", value: profile.current_role });
  if (profile.years_experience != null) metaItems.push({ label: "PRAXE", value: `${profile.years_experience} let` });
  if (candidate?.external_ref) metaItems.push({ label: "REF. Č.", value: candidate.external_ref });

  return (
    <div className="db-page">
      {/* Dark header */}
      <header className="db-header">
        <div className="db-header-inner">
          <div className="db-header-top">
            <div>
              <div className="db-header-eyebrow">KANDIDÁT · {new Date().getFullYear()}</div>
              <h1 className="db-header-title">
                {isPlaceholder ? <em style={{ opacity: 0.5, fontStyle: "italic" }}>Jméno se vytahuje…</em> : (candidate?.full_name || "…")}
              </h1>
            </div>
            <div className="db-header-nav">
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end", marginBottom: "0.5rem" }}>
                {rec && <span className={`rec-badge ${REC_CLS[rec] || ""}`}>{REC_LABEL[rec] || rec}</span>}
                {card?.overall_score != null && (
                  <span className="ghost-link" style={{ color: "#e6edf3", borderColor: "#444c56", cursor: "default" }}>
                    Skóre {card.overall_score.toFixed(1)}/5
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                {positionId && (
                  <Link to={`/positions/${positionId}`} className="ghost-link" style={{ color: "#e6edf3", borderColor: "#444c56" }}>
                    ← Detail pozice
                  </Link>
                )}
                <Link to="/" className="ghost-link" style={{ color: "#e6edf3", borderColor: "#444c56" }}>Pozice</Link>
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

        {/* Staleness warning */}
        {evaluation?.is_stale && evalStatus === "completed" && (
          <div className="stale-banner" style={{ marginBottom: "1rem" }}>
            <span className="stale-banner-icon">⚠</span>
            <span>
              {evaluation.stale_reason === "position_docs_changed"
                ? "Popis pozice byl změněn — hodnocení kandidáta může být zastaralé. Spusťte hodnocení znovu."
                : "Dokumenty kandidáta byly změněny — hodnocení může být zastaralé. Spusťte hodnocení znovu."}
            </span>
          </div>
        )}

        {/* Validation hints + Eval button */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {!hasName && <span className="pd-hint pd-hint--warn">Doplňte jméno</span>}
            {!hasEmail && <span className="pd-hint pd-hint--warn">Doplňte e-mail</span>}
            {!hasDocs && <span className="pd-hint pd-hint--warn">Nahrajte alespoň jeden dokument</span>}
            {(evalStatus === "pending" || evalStatus === "processing") && (
              <span className="pd-hint pd-hint--info">⟳ Hodnotí se…</span>
            )}
            {evalStatus === "completed" && rec && (
              <span className={`rec-badge ${REC_CLS[rec]}`}>{REC_LABEL[rec]}</span>
            )}
          </div>
          <button
            className="btn-primary"
            onClick={handleStartEval}
            disabled={!canEvaluate}
            title={!canEvaluate ? "Vyplňte jméno, e-mail a přiložte dokument" : ""}
          >
            {evaluating || evalStatus === "processing" ? "⟳ Hodnotím…" : "▶ Spustit hodnocení"}
          </button>
        </div>

        {/* Info panel */}
        {candidate && (
          <InfoPanel
            candidate={candidate}
            onSaved={(updated) => setCandidate((prev) => ({ ...prev, ...updated }))}
          />
        )}

        {/* Documents */}
        <DocumentsPanel
          candidateId={candidateId}
          documents={documents}
          onChanged={loadDocuments}
        />

        {/* Evaluation card */}
        {card && (
          <div className="card">
            <div className="table-toolbar">
              <span className="field-label">AI hodnocení</span>
              <span className="cell-muted" style={{ fontSize: "12px" }}>{card.model_used} · {card.schema_version}</span>
            </div>

            {card.recommendation_rationale && (
              <div style={{ padding: "0.75rem 1.25rem", borderBottom: "1px solid var(--line)", fontSize: "13.5px", lineHeight: 1.65, color: "var(--text-muted)" }}>
                {card.recommendation_rationale}
              </div>
            )}

            <div style={{ padding: "1rem 1.25rem", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
              <Section title="✓ Silné stránky" items={card.strengths} color="var(--good)" />
              <Section title="△ Mezery" items={card.gaps} color="var(--warn)" />
              <Section title="⚠ Red flags" items={card.red_flags} color="var(--bad)" />
            </div>

            {mustHave.length > 0 && (
              <div style={{ padding: "0 1.25rem 1rem", borderTop: "1px solid var(--line)" }}>
                <div className="eval-section-title" style={{ color: "var(--text-muted)", paddingTop: "1rem" }}>Must-have kritéria</div>
                {mustHave.map((c, i) => <CriterionBar key={i} c={c} />)}
              </div>
            )}

            {niceHave.length > 0 && (
              <div style={{ padding: "0 1.25rem 1rem", borderTop: "1px solid var(--line)" }}>
                <div className="eval-section-title" style={{ color: "var(--text-muted)", paddingTop: "1rem" }}>Nice-to-have kritéria</div>
                {niceHave.map((c, i) => <CriterionBar key={i} c={c} />)}
              </div>
            )}

            {card.interview_questions?.length > 0 && (
              <div style={{ padding: "0 1.25rem 1rem", borderTop: "1px solid var(--line)" }}>
                <Section title="? Doporučené otázky k pohovoru" items={card.interview_questions} color="var(--accent-2)" />
              </div>
            )}
          </div>
        )}

        {!card && evalStatus !== "processing" && evalStatus !== "pending" && !evaluating && (
          <div className="card" style={{ padding: "2.5rem", textAlign: "center", color: "var(--text-faint)" }}>
            {canEvaluate
              ? 'Klikněte na \u201eSpustit hodnocen\u00ed\u201c pro zah\u00e1jen\u00ed AI anal\u00fdzy.'
              : 'Vyplňte jméno, e-mail a přiložte dokument pro spuštění hodnocení.'}
          </div>
        )}
      </div>
    </div>
  );
}
