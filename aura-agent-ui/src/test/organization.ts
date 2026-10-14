import { http, HttpResponse } from "msw";

import { job } from "./fixtures";
import { API, JPEG } from "./msw/handlers";
import { server } from "./msw/server";

const saved = job().organization;

/** Aura's organization profile, saved, with what was put and what was previewed. */
export function serveOrganization() {
  const put: (typeof saved)[] = [];
  const previews: (typeof saved.brand)[] = [];
  server.use(
    http.get(`${API}/admin/organization`, () => HttpResponse.json(saved)),
    http.put(`${API}/admin/organization`, async ({ request }) => {
      const body = (await request.json()) as typeof saved;
      put.push(body);
      return HttpResponse.json(body);
    }),
    http.post(`${API}/admin/unbrander/mark-preview`, async ({ request }) => {
      previews.push((await request.json()) as typeof saved.brand);
      return new HttpResponse(JPEG, { headers: { "Content-Type": "image/jpeg" } });
    }),
  );
  return { put, previews };
}
