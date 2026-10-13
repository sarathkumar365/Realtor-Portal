import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession } from "./useSession";

/** Only a signed-in admin sees what is inside; anyone else goes to sign-in and
 * comes back to the same page after. Admin is checked at sign-in, and Aura
 * checks it again on every call. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();
  if (!session) {
    return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />;
  }
  return children;
}
