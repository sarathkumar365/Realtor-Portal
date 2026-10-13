import { http, HttpResponse } from "msw";


export const API = "http://aura.test";
export const ADMIN_TOKEN = "admin-token";
export const REALTOR_TOKEN = "realtor-token";

/** Aura as a happy admin finds it. A test overrides one handler with
 * server.use(...) to make a call fail. */
// A 1x1 JPEG is enough for <img>: tests check the image is asked for, not its pixels.
export const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);

export const handlers = [
  http.get(`${API}/admin/unbrander/jobs`, () => HttpResponse.json({ jobs: [] })),
  http.get(`${API}/admin/unbrander/limits`, () =>
    HttpResponse.json({ max_files: 10, max_file_mb: 150, max_pages: 60, can_file: true })),
  http.get(`${API}/admin/unbrander/jobs/:jobId/documents/:position/pages/:page`, () =>
    new HttpResponse(JPEG, { headers: { "Content-Type": "image/jpeg" } })),
  http.post(`${API}/login`, async ({ request }) => {
    const { user, password } = (await request.json()) as { user: string; password: string };
    if (password !== "right") return HttpResponse.json({ detail: "invalid id or password" }, { status: 401 });
    const token = user === "admin" ? ADMIN_TOKEN : REALTOR_TOKEN;
    return HttpResponse.json({ ok: true, token, name: user === "admin" ? "Sudhanshu" : "Riya", role: "realtor" });
  }),
  http.get(`${API}/me`, ({ request }) => {
    const token = request.headers.get("Authorization")?.replace("Bearer ", "");
    if (token === ADMIN_TOKEN) return HttpResponse.json({ user: "admin", role: "admin", admin: true });
    if (token === REALTOR_TOKEN) return HttpResponse.json({ user: "riya", role: "realtor", admin: false });
    return HttpResponse.json({ detail: "token did not verify" }, { status: 401 });
  }),
];
