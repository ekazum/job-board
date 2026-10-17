import { defineConfig } from "vite";

// Dev only: `npm run dev` serves on :5173 and forwards API calls to uvicorn.
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
