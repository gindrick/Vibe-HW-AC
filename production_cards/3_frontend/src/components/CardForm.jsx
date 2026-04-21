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
      setError("Uložení se nezdařilo: " + (e.response?.data?.detail || e.message));
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

      {/* Nadpis karty */}
      <div className="form-group" style={{ marginBottom: "0.45rem" }}>
        <label className="form-label">Nadpis karty</label>
        <input className="form-input" value={form.title} onChange={e => set("title", e.target.value)} />
      </div>

      {/* Výroba ABS – datum */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
        <span style={{ whiteSpace: "nowrap", fontSize: 12, color: "var(--text-dim)" }}>Výroba ABS – datum:</span>
        <input
          className="form-input"
          style={{ maxWidth: 140 }}
          value={form.date}
          onChange={e => set("date", e.target.value)}
        />
      </div>

      {/* Číslo linky / směna / obsluha */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.45rem" }}>
        <F label="Číslo výrobní linky" fieldKey="line_number" />
        <F label="Směna" fieldKey="shift" />
        <F label="Obsluha" fieldKey="operator" />
      </div>

      <HR />

      {/* Nástroj / Vyráběný rozměr / Povrchová úprava */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.35rem" }}>
        <F label="Nástroj" fieldKey="tool" />
        <F label="Vyráběný rozměr" fieldKey="produced_dimension" />
        <F label="Povrchová úprava" fieldKey="surface_treatment" />
      </div>

      {/* Číslo artiklu / Materiál / Lakování */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.45rem" }}>
        <F label="Číslo artiklu" fieldKey="article_number" />
        <F label="Materiál/Granulát" fieldKey="material_granulate" />
        <F label="Lakování (druh, poměr)" fieldKey="coating" />
      </div>

      <HR />
      <SectionLabel>Obsluha naměřeno</SectionLabel>

      {/* Tloušťka / Šířka / U profil / Povrch / Lesk */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: "0.45rem", marginBottom: "0.45rem" }}>
        <F label="Tloušťka" fieldKey="thickness" />
        <F label="Šířka" fieldKey="width" />
        <F label="U profil" fieldKey="u_profile" />
        <F label="Povrch" fieldKey="surface" />
        <F label="Lesk °" fieldKey="gloss" />
      </div>

      <HR />

      {/* Parametry procesu */}
      {form.parameters.length === 0 ? (
        <p className="text-dim text-sm" style={{ marginBottom: "0.8rem" }}>Žádné parametry nebyly vytěženy.</p>
      ) : (
        <table className="params-table" style={{ marginBottom: "0.45rem" }}>
          <thead>
            <tr>
              <th style={{ width: 28 }}>#</th>
              <th style={{ width: "33%" }}>Parametr</th>
              <th style={{ width: "33%" }}>Hodnota</th>
              <th style={{ width: "33%" }}>Jedn.</th>
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

      {/* Poznámky */}
      <div className="form-group" style={{ marginBottom: "0.45rem" }}>
        <label className="form-label">Poznámky</label>
        <textarea className="form-input" rows={2} value={form.notes}
          onChange={e => set("notes", e.target.value)} />
      </div>

      {/* Zápatí */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.45rem", marginBottom: "0.6rem" }}>
        <F label="Zpracoval" fieldKey="footer_processed_by" />
        <F label="Schválil" fieldKey="footer_approved_by" />
      </div>

      {error && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: "0.75rem" }}>{error}</div>}

      <div className="flex gap-2" style={{ alignItems: "center" }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? "Ukládám…" : "Uložit změny"}
        </button>
        {!dirty && <span className="text-dim text-sm">Uloženo</span>}
      </div>

    </div>
  );
}
