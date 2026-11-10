import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    // Lets tests resolve the "@/..." imports that the components and pages use.
    alias: [{ find: /^@\//, replacement: fileURLToPath(new URL("./", import.meta.url)) }],
  },
  test: {
    // Logic, route and middleware tests run in Node. Tests for React components and
    // pages switch to jsdom with a "// @vitest-environment jsdom" comment on line 1.
    environment: "node",
    include: [
      "lib/**/*.test.ts",
      "components/**/*.test.tsx",
      "app/**/*.test.ts",
      "app/**/*.test.tsx",
      "proxy.test.ts",
    ],
    coverage: {
      provider: "v8",
      // The logic layer, the React components, the pages and routes in app/, and the
      // login middleware are measured. See docs/COVERAGE.md for what is left out and why.
      include: ["lib/**/*.ts", "components/**/*.tsx", "app/**/*.ts", "app/**/*.tsx", "proxy.ts"],
      exclude: [
        "**/*.test.ts",
        "**/*.test.tsx",
        "lib/types.ts",
        "components/ui/Toast.tsx",
        "app/layout.tsx",
        "app/**/layout.tsx",
        "app/**/sign-in/**",
        "app/**/sign-up/**",
      ],
      reporter: ["text", "cobertura"],
      reportsDirectory: "coverage",
    },
  },
});
