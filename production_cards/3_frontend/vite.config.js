import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    base: env.VITE_PUBLIC_BASE_PATH || "/production_cards/",
    server: {
      host: "0.0.0.0",
      port: Number(env.FRONTEND_PORT || 5174),
      allowedHosts: ["all", "erp.hranipex.net"],
      hmr: {
        host: env.VITE_HMR_HOST || "localhost",
        port: Number(env.VITE_HMR_PORT || env.FRONTEND_PORT || 5174),
        protocol: env.VITE_HMR_PROTOCOL || "ws",
      },
      proxy: {
        "/production_cards_api": {
          target: "http://127.0.0.1:8011",
          rewrite: (path) => path.replace(/^\/production_cards_api/, ""),
        },
      },
    },
  };
});
