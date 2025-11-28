import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["packages/core/src/**/*.{ts,tsx}"],
      exclude: [
        "packages/core/src/**/*.d.ts",
        "packages/core/src/components/ui/**", // shadcn components
      ],
    },
  },
  resolve: {
    alias: {
      "@chimera/core": "./packages/core/src",
      "@chimera/platform": "./packages/platform/src",
    },
  },
});
