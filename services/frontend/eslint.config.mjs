import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Only present inside the frontend-dev container's tmpfs (compose.dev.yaml): the pnpm store,
    // corepack cache and HOME hold thousands of third-party files that must not be linted.
    ".pnpm-store/**",
    ".corepack/**",
    ".home/**",
  ]),
]);

export default eslintConfig;
