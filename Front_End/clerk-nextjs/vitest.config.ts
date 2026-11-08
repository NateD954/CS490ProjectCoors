import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
    coverage: {
      provider: "v8",
      // Only the logic layer is measured today. See docs/COVERAGE.md for why.
      include: ["lib/**/*.ts"],
      exclude: ["lib/**/*.test.ts", "lib/types.ts"],
      reporter: ["text", "cobertura"],
      reportsDirectory: "coverage",
    },
  },
});
