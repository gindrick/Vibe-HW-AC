import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { DropZone } from "./DropZone";

function nowLocal() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function AddPositionModal({ onClose, onSubmit, loading }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [openedAt, setOpenedAt] = useState(nowLocal);
  const [salaryFrom, setSalaryFrom] = useState("");
  const [salaryTo, setSalaryTo] = useState("");
  const [salaryVisible, setSalaryVisible] = useState(false);
  const [files, setFiles] = useState([]);
  const [textContent, setTextContent] = useState("");
  const [errors, setErrors] = useState({});
  const [maximized, setMaximized] = useState(false);
  const titleRef = useRef(null);

  // Focus first input & close on Escape
  useEffect(() => {
    titleRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && !loading && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, loading]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  function validate() {
    const errs = {};
    if (!title.trim()) errs.title = "Název pozice je povinný";
    if (!description.trim()) errs.description = "Popis pozice je povinný";
    if (!openedAt) errs.openedAt = "Datum zadání je povinné";
    if (salaryFrom === "") errs.salaryFrom = "Zadejte spodní hranici";
    else if (isNaN(Number(salaryFrom)) || Number(salaryFrom) < 0) errs.salaryFrom = "Zadejte platné číslo";
    if (salaryTo === "") errs.salaryTo = "Zadejte horní hranici";
    else if (isNaN(Number(salaryTo)) || Number(salaryTo) < 0) errs.salaryTo = "Zadejte platné číslo";
    else if (Number(salaryTo) < Number(salaryFrom)) errs.salaryTo = "Musí být větší nebo rovno spodní hranici";
    if (files.length === 0 && !textContent.trim()) errs.docs = "Nahrajte soubor nebo zadejte textový popis";
    return errs;
  }

  function handleSubmit(e) {
    e.preventDefault();
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    onSubmit({
      title: title.trim(),
      description: description.trim(),
      openedAt,
      salaryFrom: Number(salaryFrom),
      salaryTo: Number(salaryTo),
      salaryVisible,
      files,
      textContent,
    });
  }

  return createPortal(
    <div
      className="modal-overlay"
      onClick={(e) => e.target === e.currentTarget && !loading && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className={`modal${maximized ? " modal--maximized" : ""}`}>
        {/* Header */}
        <div className="modal-header">
          <h2 id="modal-title">Přidat pracovní pozici</h2>
          <div className="modal-header-actions">
            <button className="modal-close" onClick={() => setMaximized((m) => !m)} aria-label={maximized ? "Zmenšit" : "Maximalizovat"}>
              {maximized ? "⊡" : "⊞"}
            </button>
            <button className="modal-close" onClick={onClose} disabled={loading} aria-label="Zavřít">
              ×
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <div className="modal-body">
            {/* Title + Date row */}
            <div className="field-row">
              <div className="field" style={{ flex: 2 }}>
                <label className="field-label" htmlFor="pos-title">Název pozice *</label>
                <input
                  id="pos-title"
                  ref={titleRef}
                  className={`field-input ${errors.title ? "is-error" : ""}`}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="např. Senior Frontend Developer"
                  maxLength={250}
                />
                {errors.title && <span className="field-error-msg">{errors.title}</span>}
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="pos-date">Datum zadání *</label>
                <input
                  id="pos-date"
                  type="datetime-local"
                  className={`field-input ${errors.openedAt ? "is-error" : ""}`}
                  value={openedAt}
                  onChange={(e) => setOpenedAt(e.target.value)}
                />
                {errors.openedAt && <span className="field-error-msg">{errors.openedAt}</span>}
              </div>
            </div>

            {/* Description */}
            <div className="field">
              <label className="field-label" htmlFor="pos-desc">Stručný popis role *</label>
              <textarea
                id="pos-desc"
                className={`field-textarea ${errors.description ? "is-error" : ""}`}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Krátký popis pozice zobrazovaný v přehledu…"
                rows={2}
                maxLength={16000}
              />
              {errors.description && <span className="field-error-msg">{errors.description}</span>}
            </div>

            {/* Salary range */}
            <div className="field">
              <label className="field-label">Platové rozmezí (Kč / měsíc) *</label>
              <div className="salary-range-row">
                <div className="salary-range-field">
                  <span className="salary-range-label">Od</span>
                  <input
                    type="number"
                    min="0"
                    step="500"
                    className={`field-input ${errors.salaryFrom ? "is-error" : ""}`}
                    value={salaryFrom}
                    onChange={(e) => setSalaryFrom(e.target.value)}
                    placeholder="např. 60 000"
                  />
                  {errors.salaryFrom && <span className="field-error-msg">{errors.salaryFrom}</span>}
                </div>
                <span className="salary-range-sep">–</span>
                <div className="salary-range-field">
                  <span className="salary-range-label">Do</span>
                  <input
                    type="number"
                    min="0"
                    step="500"
                    className={`field-input ${errors.salaryTo ? "is-error" : ""}`}
                    value={salaryTo}
                    onChange={(e) => setSalaryTo(e.target.value)}
                    placeholder="např. 90 000"
                  />
                  {errors.salaryTo && <span className="field-error-msg">{errors.salaryTo}</span>}
                </div>
              </div>
            </div>

            {/* Salary visibility */}
            <div className="field">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={salaryVisible}
                  onChange={(e) => setSalaryVisible(e.target.checked)}
                />
                <span>Zahrnout platové rozmezí a požadavek uchazeče do AI hodnocení</span>
              </label>
            </div>

            {/* Documents */}
            <div className="field">
              <label className="field-label">
                Přílohy – job description a podklady *
              </label>
              <DropZone
                files={files}
                onFilesChange={setFiles}
                textContent={textContent}
                onTextChange={setTextContent}
              />
              {errors.docs && <span className="field-error-msg">{errors.docs}</span>}
            </div>
          </div>

          {/* Footer */}
          <div className="modal-footer">
            <button type="button" className="btn-ghost" onClick={onClose} disabled={loading}>
              Zrušit
            </button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? (
                <span className="btn-spinner">⟳ Ukládám…</span>
              ) : (
                "Vytvořit pozici"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}
