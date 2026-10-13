import { request, send } from "./client";
import type { components } from "./schema";

export type Organization = components["schemas"]["Organization-Output"];
export type Brand = components["schemas"]["Brand"];

export function getOrganization(signal?: AbortSignal): Promise<Organization> {
  return request<Organization>("/admin/organization", { signal });
}

/** Saves the profile; chat and every new Unbrander job use it at once. */
export function saveOrganization(organization: components["schemas"]["Organization-Input"]): Promise<Organization> {
  return request<Organization>("/admin/organization", { method: "PUT", json: organization });
}

/** The mark as this brand would print it, drawn by the code that marks every PDF. */
export async function previewMark(brand: Brand, signal?: AbortSignal): Promise<Blob> {
  return (await send("/admin/unbrander/mark-preview", { method: "POST", json: brand, signal })).blob();
}
