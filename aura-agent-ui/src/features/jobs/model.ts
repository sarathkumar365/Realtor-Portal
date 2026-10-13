import { type DocumentStatus, ENDED, type Finding, type JobDocument, type JobStatus, type Outcome } from "@/api/jobs";
import type { BadgeTone } from "@/components/ui/badge";

export const JOB_STATUS: Record<JobStatus, { label: string; tone: BadgeTone }> = {
  RECEIVED: { label: "Waiting", tone: "neutral" },
  UNBRANDING: { label: "Unbranding", tone: "info" },
  UNBRANDED: { label: "Ready", tone: "success" },
  FILING: { label: "Filing", tone: "info" },
  FILED_PRIVATE: { label: "Filed (private)", tone: "success" },
  FAILED: { label: "Failed", tone: "danger" },
};

export const DOCUMENT_STATUS: Record<DocumentStatus, { label: string; tone: BadgeTone }> = {
  PENDING: { label: "Waiting", tone: "neutral" },
  UNBRANDING: { label: "Unbranding", tone: "info" },
  VERIFIED: { label: "Passed checks", tone: "success" },
  BLOCKED: { label: "Blocked", tone: "danger" },
  FILED: { label: "Filed", tone: "success" },
  FAILED: { label: "Failed", tone: "danger" },
};

export const SEVERITY: Record<Finding["severity"], { label: string; tone: BadgeTone }> = {
  block: { label: "Blocks", tone: "danger" },
  retry: { label: "Retried", tone: "warning" },
  flag: { label: "For review", tone: "info" },
};

export const CHECK: Record<Finding["check"], string> = {
  text_sweep: "Name left in text",
  raw_bytes: "Name left in the file",
  ocr_sweep: "Name visible in image",
  numbers: "Number changed",
  provenance: "New text appeared",
  metadata: "Metadata",
  cover_up: "Possible cover-up",
  pages: "Pages",
  damage: "Content lost",
  visual: "Seen by the judge",
};

export const DOC_TYPE: Record<string, string> = {
  price_list: "Price list", floor_plan: "Floor plan", site_plan: "Site plan", feature_sheet: "Features",
  terms: "Terms", elevation: "Elevations", marketing: "Marketing",
};

/** A job open this long is probably stuck: the worker is off, or over its daily cap. */
export const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function isStale(status: JobStatus, createdAt: string, now = Date.now()): boolean {
  return !ENDED.has(status) && now - Date.parse(createdAt) > STALE_AFTER_MS;
}

/** The document has a cleaned file to look at. */
export function hasOutput(document: JobDocument): boolean {
  return document.status === "VERIFIED" || document.status === "BLOCKED" || document.status === "FILED";
}

export interface PagePairing {
  source: number;
  /** The output page made from it, or null when it was dropped. */
  output: number | null;
  findings: Finding[];
  droppedBecause: string | null;
}

/** Each source page with its output page and the findings on it. Findings are in
 * source page numbers (the server converts verify()'s), so they pair directly. */
export function pairPages(document: JobDocument): PagePairing[] {
  const pages = [];
  for (let page = 1; page <= document.page_count; page += 1) {
    const output = document.page_map[String(page)] ?? null;
    pages.push({
      source: page,
      output,
      findings: (document.findings ?? []).filter((finding) => finding.page === page),
      droppedBecause: output === null ? dropReason(document.removed_items ?? [], page) : null,
    });
  }
  return pages;
}

function dropReason(removed: Outcome[], page: number): string {
  const drop = removed.find((item) => item.action.tool === "drop_page" && "page" in item.action && item.action.page === page);
  return drop?.action.why ?? "dropped";
}

/** Findings about the whole file (metadata, raw bytes), not one page. */
export function wholeFileFindings(document: JobDocument): Finding[] {
  return (document.findings ?? []).filter((finding) => finding.page == null);
}

/** What was removed, without the dropped pages: those show beside their page. */
export function removals(document: JobDocument): Outcome[] {
  return (document.removed_items ?? []).filter((item) => item.action.tool !== "drop_page");
}

export function describeRemoval(item: Outcome): string {
  const action = item.action;
  switch (action.tool) {
    case "redact_terms":
      return `Names removed: ${action.terms.join(", ")}`;
    case "redact_rect":
      return `Area cleared on page ${action.page}`;
    case "remove_element":
      return `Element ${action.element_id} removed on page ${action.page}`;
    case "drop_page":
      return `Page ${action.page} dropped`;
    case "add_mark":
      return "Mark added";
  }
}
