import { defineConfig } from "vitest/config";
import tsconfigPaths from "vite-tsconfig-paths";

// Unit tests for the fork's web code (squadron); the app build uses vite.config.ts.
export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    environment: "jsdom",
    include: ["core/**/*.test.{ts,tsx}"],
  },
});
