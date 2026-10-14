import { useEffect, useRef } from "react";
import { useBlocker } from "react-router";

/** Holds a move to another page while there are unsaved changes, and asks the
 * browser to warn before a reload or close. The caller shows the question, and
 * calls `allow()` before navigating away itself after a save: the form is still
 * dirty until React re-renders, and the blocker would stop that move. */
export function useUnsavedGuard(dirty: boolean) {
  const allowed = useRef(false);
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && !allowed.current && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  return { blocker, allow: () => { allowed.current = true; } };
}
