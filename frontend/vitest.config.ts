// Unit tests of the website, the CRM and the shared package (npm test). They run in Node: the tested code is plain
// TypeScript (formatting, rules, the design tokens), so no browser is needed.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["{shared,web,crm}/src/**/*.test.{ts,tsx}"],
    environment: "node",
    // CSS is left out of tests by default; the token test reads tokens.css as text
    css: { include: [/tokens\.css/] },
  },
});
