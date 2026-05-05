import { Link } from "react-router-dom";
import { baseURL } from "../api";
import { useDarkMode } from "../hooks/useDarkMode";

export function Shell({ title, subtitle, children, backTo, backLabel }) {
  const { theme, toggle } = useDarkMode();

  return (
    <div className="page-wrap">
      <header className="hero">
        <div>
          <h1>{title}</h1>
          {subtitle && <p className="hero-sub">{subtitle}</p>}
        </div>
        <nav className="hero-nav">
          {backTo ? (
            <Link to={backTo} className="ghost-link">
              ← {backLabel || "Zpět"}
            </Link>
          ) : null}
          <Link to="/" className="ghost-link">
            Pozice
          </Link>
          <button
            className="theme-toggle"
            onClick={toggle}
            aria-label={theme === "dark" ? "Přepnout na světlý režim" : "Přepnout na tmavý režim"}
            title={theme === "dark" ? "Světlý režim" : "Tmavý režim"}
          >
            {theme === "dark" ? "☀︎" : "☽"}
          </button>
          <a href={baseURL + "/auth/logout"} className="ghost-link" style={{ fontSize: "12px", opacity: 0.6 }}>
            Odhlásit ↗
          </a>
        </nav>
      </header>
      <main>{children}</main>
    </div>
  );
}
