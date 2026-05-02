import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Configuração do Vite para o frontend da Agenda UNOESC.
 * O proxy redireciona chamadas de /api para o backend FastAPI (porta 8880),
 * eliminando problemas de CORS durante o desenvolvimento.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      "/api": {
        target: "http://localhost:8880",
        changeOrigin: true,
      },
    },
  },
});
