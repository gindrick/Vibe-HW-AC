import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { api, baseURL } from "./api";
import { AuthContext } from "./AuthContext";
import { CardsListPage } from "./pages/CardsListPage";
import { CardDetailPage } from "./pages/CardDetailPage";

const loginUrl = baseURL + "/auth/login";

function AuthGuard({ children }) {
  const [state, setState] = useState("loading");
  const [authCtx, setAuthCtx] = useState({ user: null });

  useEffect(() => {
    api.get("/auth/status")
      .then(({ data }) => {
        if (data.authenticated) {
          setAuthCtx({ user: data.user });
          setState("ok");
        } else {
          setState("redirect");
        }
      })
      .catch(() => setState("redirect"));
  }, []);

  if (state === "loading") return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#0f172a" }}>
      <div className="spinner" />
    </div>
  );
  if (state === "redirect") {
    window.location.href = loginUrl;
    return null;
  }
  return <AuthContext.Provider value={authCtx}>{children}</AuthContext.Provider>;
}

export function App() {
  return (
    <AuthGuard>
      <Routes>
        <Route path="/" element={<CardsListPage />} />
        <Route path="/cards/:cardId" element={<CardDetailPage />} />
      </Routes>
    </AuthGuard>
  );
}
