import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // strictPort: fail instead of moving to a port the backend CORS list does not allow.
  server: { port: 5173, strictPort: true },
});
