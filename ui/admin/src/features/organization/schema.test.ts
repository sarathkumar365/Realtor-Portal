import { brandSchema } from "./schema";

const brand = { mark_words: [{ text: "AURA", colour: "#0E1A24" }], font: "Times", size: 7.5, tracking: 1.6, opacity: 0.55, margin: 36 };

test("the brand rules match the server's", () => {
  expect(brandSchema.safeParse(brand).success).toBe(true);
  expect(brandSchema.safeParse({ ...brand, mark_words: [{ text: "Réalty", colour: "#0e1a24" }] }).success).toBe(true);
  for (const bad of [
    { mark_words: [] },
    { mark_words: [{ text: "AURA KEY", colour: "#0E1A24" }] },
    { mark_words: [{ text: "A1", colour: "#0E1A24" }] },
    { mark_words: [{ text: "AURA", colour: "red" }] },
    { size: 0 },
    { opacity: 1.5 },
    { tracking: -1 },
  ]) {
    expect(brandSchema.safeParse({ ...brand, ...bad }).success).toBe(false);
  }
});
