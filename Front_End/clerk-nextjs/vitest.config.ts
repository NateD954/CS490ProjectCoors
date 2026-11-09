import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    // Lets tests resolve the "@/..." imports that the components use.
    alias: [{ find: /^@\//, replacement: fileURLToPath(new URL("./", import.meta.url)) }],
  },
  test: {
    // Logic tests run in Node. Component tests switch to jsdom with a
    // "// @vitest-environment jsdom" comment on their first line.
    environment: "node",
    include: ["lib/**/*.test.ts", "components/**/*.test.tsx"],
    coverage: {
      provider: "v8",
      // The logic layer and the React components are measured.
      // See docs/COVERAGE.md for what is left out and why.
      include: ["lib/**/*.ts", "components/**/*.tsx"],
      exclude: ["**/*.test.ts", "**/*.test.tsx", "lib/types.ts", "components/ui/Toast.tsx"],
      reporter: ["text", "cobertura"],
      reportsDirectory: "coverage",
    },
  },
});
