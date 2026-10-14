import { request } from "./client";
import type { components } from "./schema";

export type SignedIn = components["schemas"]["SignedIn"];
export type Me = components["schemas"]["Me"];

export function signIn(user: string, password: string): Promise<SignedIn> {
  return request<SignedIn>("/login", { method: "POST", json: { user, password } });
}

/** Who a token belongs to, as Aura verifies it. */
export function whoIs(token: string): Promise<Me> {
  return request<Me>("/me", { token });
}
