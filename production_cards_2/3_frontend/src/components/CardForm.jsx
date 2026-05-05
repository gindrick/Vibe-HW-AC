import { useState } from "react";
import { updateCard } from "../api";

export function CardForm({ card, onSaved }) {
  const [form, setForm] = useState(buildForm(card));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);

  function buildForm(c) {
    const n = (v) => (!v || v === "null") ? "" : v;
    return {
      title:               n(c.title),
      date:                n(c.date),
      line_number:         n(c.line_number),
      shift:               n(c.shift),
      operator:            n(c.operator),
      tool:                n(c.tool),
      produced_dimension:  n(c.produced_dimension),
      surface_treatment:   n(c.surface_treatment),
      article_number:      n(c.article_number),
      material_granulate:  n(c.material_granulate),
      coating:             n(c.coating),
      thickness:           n(c.thickness),
      width:               n(c.width),
      u_profile:           n(c.u_profile),
      surface:             n(c.surface),
      gloss:               n(c.gloss),
      parameters:          (c.parameters || []).map(p => ({ ...p, name: n(p.name), value: n(p.value), unit: n(p.unit) })),
      notes:               n(c.notes),
      footer_processed_by: n(c.footer_processed_by),
      footer_approved_by:  n(c.footer_approved_by),
    };
  }

  function set(key, value) {
    setForm(prev => ({ ...prev, [key]: value }));
    setDirty(true);
  }

  function setParam(idx, key, value) {
    setForm(prev => ({
      ...prev,
      parameters: prev.parameters.map((p, i) => i === idx ? { ...p, [key]: value } : p),
    }));
    setDirty(true);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form };
      Object.keys(payload).forEach(k => {
        if (typeof payload[k] === "string" && payload[k] === "") payload[k] = null;
      });
      const saved = await updateCard(card.card_id, payload);
      setDirty(false);
      onSaved?.(saved);
    } catch (e) {
      setError("Save failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  }

  const F = ({ label, fieldKey, style }) => (
    <div className="form-group" style={style}>
      <label className="form-label">{label}</label>
      <input className="form-input" value={form[fieldKey]} onChange={e => set(fieldKey, e.target.value)} />
    </div>
  );

  const HR = () => (
    <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "0.45rem 0" }} />
  );

  const SectionLabel = ({ children }) => (
    <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: "0.3rem" }}>
      {children}
    </div>
  );

  return (
    <div>

      {/* Card title */}
      <div className="form-group" style={{ marginBottom: "0.45rem" }}>
        <label className="form-label">Card title</label>
        <input className="form-input" value={form.title} onChange={e => set("title", e.target.value)} />
      </div>

      {/* ABS Production – date */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
        <span style={{ whiteSpace: "nowrap", fontSize: 12, color: "var(--text-dim)" }}>ABS Production – date:</span>
        <input
          className="form-input"
          style={{ maxWidth: 140 }}
          value={form.date}
          onChange={e => set("date", e.target.value)}
        />
      </div>

      {/* Line number / shift / operator */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.45rem" }}>
        <F label="Production line number" fieldKey="line_number" />
        <F label="Shift" fieldKey="shift" />
        <F label="Operator" fieldKey="operator" />
      </div>

      <HR />

      {/* Tool / Produced dimension / Surface treatment */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.35rem" }}>
        <F label="Tool" fieldKey="tool" />
        <F label="Produced dimension" fieldKey="produced_dimension" />
        <F label="Surface treatment" fieldKey="surface_treatment" />
      </div>

      {/* Article number / Material / Coating */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.45rem" }}>
        <F label="Article number" fieldKey="article_number" />
        <F label="Material/Granulate" fieldKey="material_granulate" />
        <F label="Coating (type, ratio)" fieldKey="coating" />
      </div>

      <HR />
      <SectionLabel>Operator measurements</SectionLabel>

      {/* Thickness / Width / U profile / Surface / Gloss */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.45rem" }}>
        <F label="Thickness" fieldKey="thickness" />
        <F label="Width" fieldKey="width" />
        <F label="U profile" fieldKey="u_profile" />
        <F label="Surface" fieldKey="surface" />
        <F label="Gloss °" fieldKey="gloss" />
      </div>

      <HR />

      {/* Process parameters */}
      {form.parameters.length === 0 ? (
        <p className="text-dim text-sm" style={{ marginBottom: "0.8rem" }}>No parameters were extracted.</p>
      ) : (
        <table className="params-table" style={{ marginBottom: "0.45rem" }}>
          <thead>
            <tr>
              <th style={{ width: 28 }}>#</th>
              <th style={{ width: "33%" }}>Parameter</th>
              <th style={{ width: "33%" }}>Value</th>
              <th style={{ width: "33%" }}>Unit</th>
            </tr>
          </thead>
          <tbody>
            {form.parameters.map((p, i) => (
              <tr key={i}>
                <td className="text-dim text-sm font-mono" style={{ textAlign: "center" }}>{p.number}</td>
                <td>
                  <input className="form-input" style={{ width: "100%" }}
                    value={p.name} onChange={e => setParam(i, "name", e.target.value)} />
                </td>
                <td>
                  <input className="form-input" style={{ width: "100%" }}
                    value={p.value} onChange={e => setParam(i, "value", e.target.value)} />
                </td>
                <td>
                  <input className="form-input" style={{ width: "100%" }}
                    value={p.unit} onChange={e => setParam(i, "unit", e.target.value)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Notes */}
      <div className="form-group" style={{ marginBottom: "0.45rem" }}>
        <label className="form-label">Notes</label>
        <textarea className="form-input" rows={2} value={form.notes}
          onChange={e => set("notes", e.target.value)} />
      </div>

      {/* Footer */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.45rem", marginBottom: "0.6rem" }}>
        <F label="Processed by" fieldKey="footer_processed_by" />
        <F label="Approved by" fieldKey="footer_approved_by" />
      </div>

      {error && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: "0.75rem" }}>{error}</div>}

      <div className="flex gap-2" style={{ alignItems: "center" }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? "Saving…" : "Save changes"}
        </button>
        {!dirty && <span className="text-dim text-sm">Saved</span>}
      </div>

    </div>
  );
}
