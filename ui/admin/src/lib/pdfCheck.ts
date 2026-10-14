// Checked here first so a wrong file is refused before minutes of uploading; the
// server checks again and has the last word. The size limit is the server's
// (GET /admin/unbrander/limits), passed in, never a copy kept here.
const PDF_MAGIC = "%PDF-";

/** Why a file cannot be uploaded, or null when it looks like a PDF. */
export async function pdfProblem(file: File, maxMb: number): Promise<string | null> {
  if (file.size === 0) return "is empty";
  if (file.size > maxMb * 1024 ** 2) return `is larger than ${maxMb} MB`;
  // The first bytes, not the extension: a .pdf can be a renamed Word file.
  const head = new TextDecoder().decode(await file.slice(0, PDF_MAGIC.length).arrayBuffer());
  return head === PDF_MAGIC ? null : "is not a PDF";
}
