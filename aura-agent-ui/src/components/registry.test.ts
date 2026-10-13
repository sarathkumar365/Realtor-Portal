import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

// Reuse is enforced, not remembered: a shared component without an entry in
// COMPONENTS.md is a component the next screen will not know to reuse.
test("every shared component has an entry in COMPONENTS.md", () => {
  const root = process.cwd();
  const registry = readFileSync(join(root, "COMPONENTS.md"), "utf8");
  const listed = new Set([...registry.matchAll(/^### (\w+)$/gm)].map((match) => match[1] ?? ""));
  const components = readdirSync(join(root, "src", "components"))
    .filter((name) => name.endsWith(".tsx") && !name.endsWith(".test.tsx"))
    .map((name) => name.replace(/\.tsx$/, ""));
  expect(components.filter((name) => !listed.has(name))).toEqual([]);
  expect([...listed].filter((name) => !components.includes(name))).toEqual([]);
});
