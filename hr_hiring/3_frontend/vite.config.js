import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    base: env.VITE_PUBLIC_BASE_PATH || "/hr_hiring/",
    server: {
      host: "0.0.0.0",
      port: Number(env.FRONTEND_PORT || 8000),
      allowedHosts: ["all", "erp.hranipex.net"],
      hmr: {
        // When accessed via reverse proxy (e.g. erp.hranipex.net:8000),
        // tell the browser to connect HMR WebSocket to that public host/port.
        host: env.VITE_HMR_HOST || "localhost",
        port: Number(env.VITE_HMR_PORT || env.FRONTEND_PORT || 5173),
        protocol: env.VITE_HMR_PROTOCOL || "ws",
      },
      proxy: {
        "/hr_hiring_api": {
          target: "http://127.0.0.1:8010",
          rewrite: (path) => path.replace(/^\/hr_hiring_api/, ""),
        },
      },
    },
  };
});
