import { useRef, useState } from "react";

export function DropZone({ onFile, disabled }) {
  const [over, setOver] = useState(false);
  const inputRef = useRef(null);

  function handleDrop(e) {
    e.preventDefault();
    setOver(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file && file.type === "application/pdf") onFile(file);
  }

  function handleChange(e) {
    const file = e.target.files[0];
    if (file) onFile(file);
    e.target.value = "";
  }

  return (
    <div
      className={`dropzone${over ? " over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
    >
      <div className="dropzone-icon">📄</div>
      <div className="dropzone-text">
        <strong>Drop PDF here</strong> or click to select a file
      </div>
      <input ref={inputRef} type="file" accept="application/pdf" style={{ display: "none" }} onChange={handleChange} />
    </div>
  );
}
