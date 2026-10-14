// The brokerage is in Toronto; admins read times there wherever the browser is.
const ZONE = "America/Toronto";

const dateTime = new Intl.DateTimeFormat("en-CA", {
  timeZone: ZONE, year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});
const time = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, hour: "numeric", minute: "2-digit", second: "2-digit" });

const day = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, weekday: "short", day: "numeric", month: "short" });
const monthName = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, month: "short" });
const hour = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, hour: "numeric", hourCycle: "h23" });
const yearMonth = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, year: "numeric", month: "2-digit" });

/** "Tue, Oct 14", in Toronto. */
export function formatDay(date: Date): string {
  return day.format(date);
}

/** "Oct", in Toronto. */
export function formatMonth(date: Date): string {
  return monthName.format(date);
}

/** "Good morning", "Good afternoon" or "Good evening", by the hour in Toronto. */
export function greeting(date: Date): string {
  const now = Number(hour.format(date));
  return now < 12 ? "Good morning" : now < 18 ? "Good afternoon" : "Good evening";
}

/** Midnight on the first of `date`'s month in Toronto, as an ISO time with its offset. */
export function startOfMonth(date: Date): string {
  const parts = Object.fromEntries(yearMonth.formatToParts(date).map((part) => [part.type, part.value]));
  // At 05:00 UTC on the first it is midnight (EST, -5) or 1 am (EDT, -4) in
  // Toronto, so the hour there gives the offset. Clocks change at 2 am, never in
  // the first hours of a month. Read from the hour rather than timeZoneName:
  // "longOffset" throws in older Safari.
  const first = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, 1, 5));
  const offset = Number(hour.format(first)) - 5;
  return `${parts.year}-${parts.month}-01T00:00:00-0${-offset}:00`;
}

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
