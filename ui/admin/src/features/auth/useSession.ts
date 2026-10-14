import { useSyncExternalStore } from "react";

import { getSession, type Session, subscribe } from "./session";

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSession);
}
