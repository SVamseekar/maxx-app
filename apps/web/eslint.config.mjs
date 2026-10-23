import js from "@eslint/js";
import tseslint from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";
import { defineConfig, globalIgnores } from "eslint/config";
export default defineConfig([
  globalIgnores([".next/**", ".next-ui-review/**", "next-env.d.ts"]),
  { files: ["**/*.{ts,tsx}"], extends: [js.configs.recommended, ...tseslint.configs.recommended] },
  { files: ["**/*.{ts,tsx}"], plugins: { "react-hooks": hooks }, rules: {
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
  } },
]);
