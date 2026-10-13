import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// The folder rules in AGENTS.md, enforced rather than remembered.
const FEATURES = ["auth", "jobs", "organization"];
const NETWORK = {
  selector: "CallExpression[callee.name='fetch'], NewExpression[callee.name='XMLHttpRequest']",
  message: "Only src/api/ talks to the network. Add a function there and call it.",
};
const NO_FEATURES = { group: ["@/features/*", "**/features/*"], message: "components/ is shared: it never imports a feature." };
const NO_APP = { group: ["@/app/*", "**/app/*"], message: "Only the shell imports app/." };

export default tseslint.config(
  { ignores: ["dist", "src/api/schema.d.ts"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended, reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite],
    languageOptions: { globals: globals.browser },
    rules: {
      "no-restricted-syntax": ["error", NETWORK],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    files: ["src/api/**"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    files: ["src/components/**", "src/lib/**"],
    rules: { "no-restricted-imports": ["error", { patterns: [NO_FEATURES, NO_APP] }] },
  },
  ...FEATURES.map((feature) => ({
    files: [`src/features/${feature}/**`],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [
          NO_APP,
          {
            group: FEATURES.filter((other) => other !== feature).map((other) => `@/features/${other}/*`),
            message: "A feature never imports another feature. Move what both need to components/ or lib/.",
          },
        ],
      }],
    },
  })),
  {
    files: ["src/test/**", "**/*.test.{ts,tsx}"],
    rules: { "no-restricted-syntax": "off", "no-restricted-imports": "off" },
  },
);
