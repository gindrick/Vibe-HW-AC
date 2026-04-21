import { Link } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { baseURL } from "../api";

export function Shell({ title, children }) {
  const { user } = useAuth();

  return (
    <div className="shell">
      <header className="shell-header">
        <Link to="/" className="shell-brand">
          <div className="shell-dot" />
          <span className="shell-name">Hranipex · Výrobní karty</span>
        </Link>
        {title && <span className="shell-title">{title}</span>}
        <div className="shell-spacer" />
        {user && <span className="shell-user">{user.name || user.email}</span>}
        <a href={baseURL + "/auth/logout"} className="btn btn-secondary btn-sm">Odhlásit</a>
      </header>
      <main className="shell-main">{children}</main>
    </div>
  );
}
