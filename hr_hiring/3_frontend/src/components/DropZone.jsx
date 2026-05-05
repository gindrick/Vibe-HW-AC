import { useCallback, useRef, useState } from "react";

const ACCEPTED = ".pdf,.doc,.docx,.txt,.md,.odt,.rtf";

export function DropZone({ files, onFilesChange, textContent, onTextChange }) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef(null);

  const addFiles = useCallback(
    (incoming) => {
      const arr = Array.from(incoming);
      onFilesChange((prev) => {
        const names = new Set(prev.map((f) => f.name));
        return [...prev, ...arr.filter((f) => !names.has(f.name))];
      });
    },
    [onFilesChange]
  );

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    addFiles(e.dataTransfer.files);
  };

  return (
    <div className="dropzone-wrap">
      {/* Drop area */}
      <div
        className={`dropzone ${isDragging ? "dropzone-active" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragEnter={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        aria-label="Oblast pro nahrání souborů"
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED}
          style={{ display: "none" }}
          onChange={(e) => addFiles(e.target.files)}
        />
        <span className="dropzone-icon">📎</span>
        <p className="dropzone-label">
          Přetáhněte soubory sem nebo <span className="dropzone-link">vyberte kliknutím</span>
        </p>
        <p className="dropzone-hint">PDF, DOCX, TXT · více souborů najednou</p>
      </div>

      {/* File pills */}
      {files.length > 0 && (
        <ul className="file-list" role="list">
          {files.map((f) => (
            <li key={f.name} className="file-pill">
              <span className="file-pill-icon">📄</span>
              <span className="file-pill-name" title={f.name}>
                {f.name.length > 36 ? f.name.slice(0, 34) + "…" : f.name}
              </span>
              <span className="file-pill-size">{formatSize(f.size)}</span>
              <button
                type="button"
                className="file-pill-remove"
                onClick={(e) => { e.stopPropagation(); onFilesChange((prev) => prev.filter((x) => x.name !== f.name)); }}
                aria-label={`Odebrat ${f.name}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Text fallback — shown only when no files */}
      {files.length === 0 && (
        <div className="text-fallback">
          <div className="text-fallback-or">
            <span>nebo zadejte text popis pozice</span>
          </div>
          <textarea
            className="field-textarea"
            placeholder="Popište požadavky, odpovědnosti, benefity a další informace o pozici…"
            value={textContent}
            onChange={(e) => onTextChange(e.target.value)}
            rows={4}
          />
        </div>
      )}
    </div>
  );
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
