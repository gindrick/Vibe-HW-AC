import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { api, baseURL } from "./api";
import { AuthContext } from "./AuthContext";
import { CandidateDetailPage } from "./pages/CandidateDetailPage";
import { PositionDashboardPage } from "./pages/PositionDashboardPage";
import { PositionDetailPage } from "./pages/PositionDetailPage";
import { PositionsPage } from "./pages/PositionsPage";

const loginUrl = baseURL + "/auth/login";

const TEST_MODE_ALLOWED_USER = "jindrich.jansa";

function AuthGuard({ children }) {
  const [state, setState] = useState("loading"); // "loading" | "ok" | "redirect"
  const [authCtx, setAuthCtx] = useState({ user: null, testMode: false });

  useEffect(() => {
    api.get("/auth/status")
      .then(({ data }) => {
        if (data.authenticated) {
          const userEmail = data.user?.email || "";
          const userLogin = userEmail.split("@")[0].toLowerCase();
          setAuthCtx({
            user: data.user,
            testMode: Boolean(data.test_mode),
            canAddCandidate: !data.test_mode || userLogin === TEST_MODE_ALLOWED_USER,
          });
          setState("ok");
        } else {
          setState("redirect");
        }
      })
      .catch(() => setState("redirect"));
  }, []);

  if (state === "loading") return null;
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
        <Route path="/" element={<PositionsPage />} />
        <Route path="/positions/:positionId" element={<PositionDetailPage />} />
        <Route path="/positions/:positionId/dashboard" element={<PositionDashboardPage />} />
        <Route path="/candidates/:candidateId" element={<CandidateDetailPage />} />
      </Routes>
    </AuthGuard>
  );
}
