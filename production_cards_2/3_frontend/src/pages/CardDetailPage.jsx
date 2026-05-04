import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { exportCardUrl, getCard } from "../api";
import { CardForm } from "../components/CardForm";
import { PdfPreview } from "../components/PdfPreview";
import { Shell } from "../components/Shell";

const STATUS_LABELS = {
  processing: "Processing",
  ready: "Ready",
  exported: "Exported",
  error: "Error",
};

export function CardDetailPage() {
  const { cardId } = useParams();
  const navigate = useNavigate();
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  async function load() {
    try {
      const data = await getCard(cardId);
      setCard(data);
      setLoading(false);
      if (data.status === "processing") {
        pollRef.current = setTimeout(load, 2500);
      }
    } catch (e) {
      setError("Failed to load card.");
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    return () => clearTimeout(pollRef.current);
  }, [cardId]);

  function handleExport() {
    window.location.href = exportCardUrl(cardId);
  }

  if (loading) return (
    <Shell>
      <div className="processing-state" style={{ marginTop: "4rem" }}>
        <div className="spinner" />
        <span>Loading card…</span>
      </div>
    </Shell>
  );

  if (error) return (
    <Shell>
      <div style={{ padding: "2rem", color: "var(--danger)" }}>{error}</div>
    </Shell>
  );

  return (
    <Shell title={card.original_filename}>
      {/* Top bar */}
      <div className="flex justify-between flex-center mb-4" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
        <div className="flex gap-3 flex-center">
          <button className="btn btn-secondary btn-sm" onClick={() => navigate(-1)}>← Back</button>
          <span className={`badge badge-${card.status}`}>{STATUS_LABELS[card.status] || card.status}</span>
          {card.model_used && (
            <span className="text-dim text-sm">model: {card.model_used}</span>
          )}
        </div>
        <div className="flex gap-2">
          <button className="btn btn-success" onClick={handleExport} disabled={card.status === "processing"}>
            ⬇ Download XLSX
          </button>
        </div>
      </div>

      {card.status === "processing" ? (
        <div className="processing-state card">
          <div className="spinner" />
          <span>Extracting data from PDF…</span>
          <span className="text-dim text-sm">The page will automatically refresh.</span>
        </div>
      ) : card.status === "error" ? (
        <div className="card" style={{ padding: "2rem", color: "var(--danger)" }}>
          Extraction failed. Try uploading the PDF again or contact the administrator.
        </div>
      ) : (
        <div className="split">
          {/* PDF Preview */}
          <PdfPreview cardId={cardId} />

          {/* Edit form */}
          <div className="card">
            <div className="section-heading mb-3">Extracted data — edit and save</div>
            <CardForm card={card} onSaved={(updated) => setCard(updated)} />
          </div>
        </div>
      )}
    </Shell>
  );
}
