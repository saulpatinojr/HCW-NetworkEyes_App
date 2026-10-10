// ESLint flat config for the web tier (TODO.md → T-419).
//
// `next lint` was removed in Next.js 16, so `npm run lint` runs ESLint directly
// with the flat config eslint-config-next publishes for exactly this purpose:
// the Next.js core-web-vitals rules plus the TypeScript layer. Build output and
// generated code are not ours to lint.
import { defineConfig, globalIgnores } from "eslint/config";
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  globalIgnores([".next/**", "node_modules/**", "next-env.d.ts"]),
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    // prisma/seed-local-admin.js is deliberately plain CommonJS: the migrator
    // image runs it with bare `node` and carries no compiled lib/ tree.
    files: ["prisma/**/*.js"],
    languageOptions: { sourceType: "commonjs" },
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
]);
