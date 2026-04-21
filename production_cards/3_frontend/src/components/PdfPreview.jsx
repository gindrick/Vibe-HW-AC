import { useEffect, useRef, useState } from "react";
import { getPdfPage } from "../api";

export function PdfPreview({ cardId }) {
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);
  const dragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (!cardId) return;
    setLoading(true);
    getPdfPage(cardId, page)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [cardId, page]);

  // Reset zoom when page changes
  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [page]);

  // Wheel zoom — must be non-passive to preventDefault
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    function onWheel(e) {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      setZoom(z => {
        const next = Math.max(1, Math.min(5, z * factor));
        if (next === 1) setPan({ x: 0, y: 0 });
        return next;
      });
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const didDrag = useRef(false);

  function onMouseDown(e) {
    didDrag.current = false;
    if (zoom <= 1) return;
    dragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
    e.preventDefault();
  }

  function onMouseMove(e) {
    if (!dragging.current) return;
    const dx = e.clientX - lastPos.current.x;
    const dy = e.clientY - lastPos.current.y;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) didDrag.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
    setPan(p => ({ x: p.x + dx, y: p.y + dy }));
  }

  function onMouseUp() { dragging.current = false; }

  function onClick(e) {
    if (didDrag.current) return;
    if (isZoomed) {
      resetZoom();
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const newZoom = 2.5;
    setPan({ x: rect.width / 2 - newZoom * cx, y: rect.height / 2 - newZoom * cy });
    setZoom(newZoom);
  }

  function resetZoom() {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  if (!cardId) return null;

  const isZoomed = zoom > 1.01;

  return (
    <div className="pdf-preview card">
      {/* Zoom hint / indicator */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.4rem", flexShrink: 0 }}>
        <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
          {isZoomed ? "táhni pro posun" : "scroll pro zoom"}
        </span>
        {isZoomed && (
          <button className="btn btn-secondary btn-sm" onClick={resetZoom} style={{ fontSize: 10, padding: "0.15rem 0.5rem" }}>
            {Math.round(zoom * 100)}% — reset
          </button>
        )}
      </div>

      {/* Image viewport */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
          borderRadius: 8,
          cursor: isZoomed ? (dragging.current ? "grabbing" : "grab") : "zoom-in",
          userSelect: "none",
        }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        onClick={onClick}
      >
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
            <div className="spinner" />
          </div>
        )}
        {!loading && data?.page_b64 && (
          <img
            src={`data:image/png;base64,${data.page_b64}`}
            alt={`Strana ${page + 1}`}
            draggable={false}
            style={{
              width: "100%",
              display: "block",
              border: "1px solid var(--border)",
              borderRadius: 8,
              transformOrigin: "top left",
              transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
              transition: dragging.current ? "none" : "transform 0.1s ease",
            }}
          />
        )}
        {!loading && !data?.page_b64 && (
          <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-dim)" }}>
            Náhled není dostupný
          </div>
        )}
      </div>

      {data && data.page_count > 1 && (
        <div className="pdf-nav">
          <button className="btn btn-secondary btn-sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>←</button>
          <span className="text-dim text-sm">Strana {page + 1} / {data.page_count}</span>
          <button className="btn btn-secondary btn-sm" onClick={() => setPage(p => Math.min(data.page_count - 1, p + 1))} disabled={page >= data.page_count - 1}>→</button>
        </div>
      )}
    </div>
  );
}
