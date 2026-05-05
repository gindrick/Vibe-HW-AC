import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { MsalProvider } from "@azure/msal-react";

import { msalInstance, msalEnabled } from "./msal";
import { App } from "./App";
import "./styles.css";

const basePath = (import.meta.env.VITE_PUBLIC_BASE_PATH || "/hr_hiring/").replace(/\/$/, "");

async function bootstrap() {
  if (msalEnabled) {
    await msalInstance.initialize();
  }

  const tree = (
    <React.StrictMode>
      <BrowserRouter basename={basePath}>
        <App />
      </BrowserRouter>
    </React.StrictMode>
  );

  createRoot(document.getElementById("root")).render(
    msalEnabled
      ? <MsalProvider instance={msalInstance}>{tree}</MsalProvider>
      : tree
  );
}

bootstrap();
