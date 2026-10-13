// The brokerage is in Toronto; admins read times there wherever the browser is.
const ZONE = "America/Toronto";

const dateTime = new Intl.DateTimeFormat("en-CA", {
  timeZone: ZONE, year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});
const time = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, hour: "numeric", minute: "2-digit", second: "2-digit" });

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

export function formatTime(iso: string | null | undefined): string {
  return iso ? time.format(new Date(iso)) : "—";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function formatMoney(usd: number | null | undefined): string {
  return usd == null ? "—" : `US$${usd.toFixed(usd < 1 ? 3 : 2)}`;
}
