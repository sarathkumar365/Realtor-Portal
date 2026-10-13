/**
 * The signed-in admin, kept in sessionStorage: it ends with the tab, and a
 * script on another site cannot read it. Storage can throw (private mode,
 * blocked site data), so every access is guarded and the app still works for
 * the life of the page.
 */
export interface Session {
  token: string;
  user: string;
  name: string;
}

const KEY = "aura-agent.session";
let current: Session | null = load();
let endReason: string | null = null;
const listeners = new Set<() => void>();

function load(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function changed(): void {
  for (const listener of listeners) listener();
}

export function getSession(): Session | null {
  return current;
}

export function startSession(session: Session): void {
  current = session;
  endReason = null;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // kept in memory only
  }
  changed();
}

/** `reason` is shown on the sign-in screen. */
export function endSession(reason: string | null = null): void {
  current = null;
  endReason = reason;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing stored
  }
  changed();
}

/** Why the last session ended; cleared when the next one starts. Not cleared on
 * read: StrictMode renders twice, and the second render must see it too. */
export function getEndReason(): string | null {
  return endReason;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
