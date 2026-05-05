import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getPositionDashboard, startEvaluation } from "../api";
import { useDarkMode } from "../hooks/useDarkMode";

const REC = {
  DOPORUCIT: { label: "Nejlepší shoda", cls: "rec-badge--best" },
  ZVAZIT: { label: "Zvážit", cls: "rec-badge--consider" },
  NEDOPORUCIT: { label: "Nevhodný", cls: "rec-badge--no" },
};

function ScorePill({ score, max = 5 }) {
  if (score == null) return null;
  const pct = Math.round((score / max) * 100);
  const color = score >= 3.5 ? "#3fb950" : score >= 2.5 ? "#d29922" : "#f85149";
  return (
    <div className="db-score-pill" style={{ "--score-color": color }}>
      <svg viewBox="0 0 36 36" className="db-score-ring">
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeOpacity=".15" strokeWidth="3" />
        <circle
          cx="18" cy="18" r="15.9" fill="none"
          stroke={color} strokeWidth="3"
          strokeDasharray={`${pct} 100`}
          strokeLinecap="round"
          transform="rotate(-90 18 18)"
        />
      </svg>
      <span className="db-score-num">{score.toFixed(1)}</span>
    </div>
  );
}

function CriterionBar({ criterion }) {
  const pct = Math.round(((criterion.score || 0) / 5) * 100);
  const color =
    criterion.score >= 4 ? "var(--good)" :
    criterion.score >= 3 ? "var(--warn)" :
    "var(--bad)";
  return (
    <div className="db-crit-row">
      <span className="db-crit-name" title={criterion.name}>
        {criterion.name.length > 28 ? criterion.name.slice(0, 26) + "…" : criterion.name}
      </span>
      <div className="db-crit-bar-track">
        <div className="db-crit-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="db-crit-score" style={{ color }}>{criterion.score}/5</span>
    </div>
  );
}

function CandidateCard({ item, onEvaluate, evaluating }) {
  const rec = REC[item.recommendation] || null;
  const mustHave = item.card?.criteria?.filter((c) => c.criterion_type === "must_have") || [];
  const niceHave = item.card?.criteria?.filter((c) => c.criterion_type === "nice_to_have") || [];
  const strengths = item.card?.strengths || [];
  const rationale = item.card?.recommendation_rationale || "";

  return (
    <div className={`db-card ${item.recommendation ? `db-card--${item.recommendation.toLowerCase()}` : ""}`}>
      <div className="db-card-head">
        {rec && <span className={`rec-badge ${rec.cls}`}>{rec.label}</span>}
        <ScorePill score={item.overall_score} />
      </div>

      <Link to={`/candidates/${item.candidate_id}`} className="db-card-name">
        {item.full_name}
      </Link>
      {item.email && <div className="db-card-email">{item.email}</div>}

      {!item.evaluation_status || item.evaluation_status === null ? (
        <div className="db-no-eval">
          <span className="cell-muted" style={{ fontSize: "12px" }}>Hodnocení nezahájeno</span>
          <button
            className="btn-outline-sm"
            disabled={evaluating}
            onClick={() => onEvaluate(item.candidate_id)}
          >
            {evaluating ? "⟳" : "▶ Hodnotit"}
          </button>
        </div>
      ) : item.evaluation_status === "processing" ? (
        <div className="db-no-eval">
          <span className="status-badge badge-warn">⟳ Hodnotí se…</span>
        </div>
      ) : item.card ? (
        <>
          {mustHave.length > 0 && (
            <div className="db-crit-section">
              {mustHave.slice(0, 4).map((c, i) => (
                <CriterionBar key={i} criterion={c} />
              ))}
            </div>
          )}

          {strengths.length > 0 && (
            <div className="db-tags">
              {strengths.slice(0, 4).map((s, i) => (
                <span key={i} className="db-tag">{s.length > 22 ? s.slice(0, 20) + "…" : s}</span>
              ))}
            </div>
          )}

          {rationale && (
            <p className="db-rationale">
              {rationale.length > 140 ? rationale.slice(0, 138) + "…" : rationale}
            </p>
          )}

          {niceHave.length > 0 && (
            <div className="db-nice-row">
              {niceHave.slice(0, 3).map((c, i) => (
                <span key={i} className={`db-nice-pill ${c.score >= 3 ? "db-nice--ok" : "db-nice--gap"}`}>
                  {c.name.length > 18 ? c.name.slice(0, 16) + "…" : c.name}
                </span>
              ))}
            </div>
          )}
        </>
      ) : null}

      <div className="db-card-footer">
        <Link to={`/candidates/${item.candidate_id}`} className="ghost-link" style={{ fontSize: "12px", padding: "0.3rem 0.7rem" }}>
          Detail →
        </Link>
      </div>
    </div>
  );
}

export function PositionDashboardPage() {
  const { positionId } = useParams();
  const { theme, toggle } = useDarkMode();
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("all");
  const [evaluatingId, setEvaluatingId] = useState(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const d = await getPositionDashboard(positionId);
      setData(d);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [positionId]);

  async function handleEvaluate(candidateId) {
    setEvaluatingId(candidateId);
    try {
      await startEvaluation(candidateId);
      await load();
    } finally {
      setEvaluatingId(null);
    }
  }

  // Derive priority criteria from the first completed evaluation
  const priorities = useMemo(() => {
    if (!data?.candidates) return [];
    for (const c of data.candidates) {
      const must = c.card?.criteria?.filter((x) => x.criterion_type === "must_have") || [];
      if (must.length) return must.slice(0, 4);
    }
    return [];
  }, [data]);

  const filtered = useMemo(() => {
    if (!data?.candidates) return [];
    if (filter === "all") return data.candidates;
    if (filter === "DOPORUCIT") return data.candidates.filter((c) => c.recommendation === "DOPORUCIT");
    if (filter === "ZVAZIT") return data.candidates.filter((c) => c.recommendation === "ZVAZIT");
    if (filter === "NEDOPORUCIT") return data.candidates.filter((c) => c.recommendation === "NEDOPORUCIT");
    if (filter === "pending") return data.candidates.filter((c) => !c.evaluation_status || c.evaluation_status === "pending");
    return data.candidates;
  }, [data, filter]);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", color: "var(--text-muted)" }}>
        ⟳ Načítám…
      </div>
    );
  }

  const s = data?.stats || {};

  return (
    <div className="db-page">
      {/* Dark header */}
      <header className="db-header">
        <div className="db-header-inner">
          <div className="db-header-top">
            <div>
              <div className="db-header-eyebrow">VÝBĚROVÉ ŘÍZENÍ · {new Date().getFullYear()}</div>
              <h1 className="db-header-title">{data?.title || "Pozice"}</h1>
            </div>
            <div className="db-header-nav">
              <Link to={`/positions/${positionId}`} className="ghost-link" style={{ color: "#e6edf3", borderColor: "#444c56" }}>
                ← Správa kandidátů
              </Link>
              <Link to="/" className="ghost-link" style={{ color: "#e6edf3", borderColor: "#444c56" }}>
                Pozice
              </Link>
              <button className="theme-toggle" onClick={toggle} style={{ borderColor: "#444c56", color: "#e6edf3" }}>
                {theme === "dark" ? "☀︎" : "☽"}
              </button>
            </div>
          </div>

          {priorities.length > 0 && (
            <div className="db-priorities">
              {priorities.map((p, i) => (
                <div key={i} className="db-priority-item">
                  <span className="db-priority-label">PRIORITA #{i + 1}</span>
                  <span className="db-priority-name">{p.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="db-body">
        {/* Stats */}
        <div className="db-stats">
          <div className="db-stat">
            <span className="db-stat-num" style={{ color: "var(--text)" }}>{s.total || 0}</span>
            <span className="db-stat-label">CELKEM KANDIDÁTŮ</span>
          </div>
          <div className="db-stat">
            <span className="db-stat-num" style={{ color: "var(--good)" }}>{s.recommended || 0}</span>
            <span className="db-stat-label">NEJLEPŠÍ SHODA</span>
          </div>
          <div className="db-stat">
            <span className="db-stat-num" style={{ color: "var(--warn)" }}>{s.consider || 0}</span>
            <span className="db-stat-label">ČÁSTEČNÁ SHODA</span>
          </div>
          <div className="db-stat">
            <span className="db-stat-num" style={{ color: "var(--bad)" }}>{s.not_recommended || 0}</span>
            <span className="db-stat-label">NEVHODNÝ</span>
          </div>
          <div className="db-stat">
            <span className="db-stat-num" style={{ color: "var(--text-muted)" }}>{s.pending || 0}</span>
            <span className="db-stat-label">ČEKÁ NA HODNOCENÍ</span>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="db-filters">
          {[
            { key: "all", label: "Všichni" },
            { key: "DOPORUCIT", label: "Nejlepší shoda" },
            { key: "ZVAZIT", label: "Částečná shoda" },
            { key: "NEDOPORUCIT", label: "Nevhodný" },
            { key: "pending", label: "Čeká" },
          ].map(({ key, label }) => (
            <button
              key={key}
              className={`db-filter-btn ${filter === key ? "db-filter-btn--active" : ""}`}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Card grid */}
        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-faint)" }}>
            Žádní kandidáti v této kategorii.
          </div>
        ) : (
          <div className="db-grid">
            {filtered.map((item) => (
              <CandidateCard
                key={item.candidate_id}
                item={item}
                onEvaluate={handleEvaluate}
                evaluating={evaluatingId === item.candidate_id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
