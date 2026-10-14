import { pdfProblem } from "./pdfCheck";

const file = (content: string, name = "x.pdf") => new File([content], name, { type: "application/pdf" });

test("a file is judged by its first bytes, not its name", async () => {
  expect(await pdfProblem(file("%PDF-1.7 ..."), 150)).toBeNull();
  expect(await pdfProblem(file("PK\u0003\u0004 a docx"), 150)).toBe("is not a PDF");
  expect(await pdfProblem(file(""), 150)).toBe("is empty");
});

test("a file over the limit is refused before upload", async () => {
  const big = file("%PDF-");
  Object.defineProperty(big, "size", { value: 151 * 1024 ** 2 });
  expect(await pdfProblem(big, 150)).toBe("is larger than 150 MB");
  expect(await pdfProblem(big, 200)).toBeNull();
});
