import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, ExternalLink, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { type ReactNode, useEffect, useRef } from "react";

import { download } from "@/api/download";
import { type Job, outputPdfPath, pageImage, type PageVersion } from "@/api/jobs";
import { AuthImage } from "@/components/AuthImage";
import { DownloadButton } from "@/components/DownloadButton";
import { StatusMark } from "@/components/StatusMark";
import { cn } from "@/lib/cn";

import {
  CHECK, changesByPage, describeRemoval, DOCUMENT_STATUS, documentName, hasOutput, pairPages, removalKind, removals,
  SEVERITY,
  wholeFileFindings,
} from "../model";

const pageKey = (jobId: string, position: number, page: number, version: PageVersion) =>
  ["page", jobId, position, page, version] as const;

/**
 * One document, full screen: the builder's page on the left, the cleaned page on
 * the right, both fit to the height so nothing scrolls. Arrows and ← → turn the
 * page; Esc closes. The page's changes are listed underneath: the worker does not
 * save where on the page each one was, so they are not drawn on it.
 */
export function ReviewViewer({ job, position, page, onPage, onDocument, onClose }: {
  job: Job;
  position: number;
  page: number;
  onPage: (page: number) => void;
  onDocument: (position: number) => void;
  onClose: () => void;
}) {
  const documents = job.documents ?? [];
  const document = documents.find((candidate) => candidate.position === position) ?? documents[0];
  const queryClient = useQueryClient();
  const last = document?.page_count ?? 1;
  const current = Math.min(Math.max(page, 1), last);

  // Read through a ref: two key presses can land before the page re-renders, and
  // the second must turn from the page the first one reached.
  const shown = useRef(current);
  useEffect(() => {
    shown.current = current;
  }, [current]);
  useEffect(() => {
    function turn(event: KeyboardEvent) {
      // A focused select or field uses the arrows itself: the document select
      // would change document and page on one key press.
      if (event.target instanceof HTMLSelectElement || event.target instanceof HTMLInputElement
        || event.target instanceof HTMLTextAreaElement) return;
      const at = shown.current;
      const next = event.key === "ArrowRight" ? at + 1 : event.key === "ArrowLeft" ? at - 1 : at;
      if (next === at || next < 1 || next > last) return;
      shown.current = next;
      onPage(next);
    }
    window.addEventListener("keydown", turn);
    return () => window.removeEventListener("keydown", turn);
  }, [last, onPage]);

  // The next page is usually the next thing looked at; fetch it before the click.
  useEffect(() => {
    if (!document || current >= last) return;
    // A dropped page has no output to fetch: the server answers 404.
    const kept = hasOutput(document) && document.page_map[String(current + 1)] != null;
    const versions: PageVersion[] = kept ? ["source", "output"] : ["source"];
    for (const version of versions) {
      void queryClient.prefetchQuery({
        queryKey: pageKey(job.id, document.position, current + 1, version),
        queryFn: ({ signal }) => pageImage(job.id, document.position, current + 1, version, signal),
        staleTime: Infinity,
      });
    }
  }, [queryClient, job.id, document, current, last]);

  if (!document) return null;
  const pairing = pairPages(document)[current - 1]!;
  const cleaned = hasOutput(document);
  // Dropped pages included: a drop is a change on that page too.
  const onPageChanges = (document.removed_items ?? []).filter((item) => "page" in item.action && item.action.page === current);
  const acrossDocument = removals(document).filter((item) => !("page" in item.action));
  const wholeFindings = wholeFileFindings(document);
  const hasWholeDocument = acrossDocument.length > 0 || wholeFindings.length > 0;
  const pagesWithChanges = changesByPage(document);
  const status = DOCUMENT_STATUS[document.status];
  const image = (version: PageVersion, alt: string) => (
    <AuthImage fit alt={alt} className="h-full w-full"
      queryKey={pageKey(job.id, document.position, current, version)}
      load={(signal) => pageImage(job.id, document.position, current, version, signal)} />
  );

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Content aria-describedby={undefined}
          // Focus the viewer itself, not its first tab: the keys turn pages from anywhere.
          onOpenAutoFocus={(event) => { event.preventDefault(); (event.currentTarget as HTMLElement | null)?.focus(); }}
          className="surface-dark fixed inset-0 z-50 grid grid-rows-[auto_minmax(0,1fr)_auto] bg-background text-foreground
            animate-[rise_0.3s_var(--ease-spring)_both] focus:outline-none">
          <header className="flex flex-wrap items-center gap-[18px] border-b border-line-2 px-5 py-3.5">
            <div className="flex min-w-0 flex-col gap-[3px]">
              <span className="label-caps">{job.project}</span>
              <Dialog.Title className="text-[14px] font-medium">{documentName(document)}</Dialog.Title>
            </div>
            {documents.length > 1 && (
              <nav aria-label="Documents" className="flex gap-0.5 max-[820px]:hidden">
                {documents.map((other) => (
                  <button key={other.id} type="button" onClick={() => onDocument(other.position)}
                    aria-current={other.position === document.position ? "true" : undefined}
                    className={cn("rounded-[4px] px-2.5 py-[7px] font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-fg-3 transition-colors hover:text-fg-2",
                      other.position === document.position && "bg-foreground text-background hover:text-background")}>
                    {documentName(other)}<span className="ml-1.5 tracking-normal opacity-60">{other.page_count}</span>
                  </button>
                ))}
              </nav>
            )}
            {documents.length > 1 && (
              // The tabs do not fit a phone's width; the same choice as a list.
              <select aria-label="Document" value={document.position} onChange={(event) => onDocument(Number(event.target.value))}
                className="order-last hidden h-[34px] basis-full rounded-[4px] border border-line bg-raise px-2.5 font-mono text-[12px] uppercase tracking-[0.14em] text-foreground
                  focus:border-foreground focus:outline-none max-[820px]:block">
                {documents.map((other) => (
                  <option key={other.id} value={other.position}>{documentName(other)} · {other.page_count}</option>
                ))}
              </select>
            )}
            <div className="ml-auto flex items-center gap-3">
              <StatusMark kind={status.kind}>{status.label}</StatusMark>
              {document.drive_file_id && (
                <a className="label-caps inline-flex items-center gap-1 hover:text-foreground" target="_blank" rel="noreferrer"
                  href={`https://drive.google.com/file/d/${encodeURIComponent(document.drive_file_id)}/view`}>
                  Open in Drive<ExternalLink className="size-3" aria-hidden />
                </a>
              )}
              {cleaned && (
                <DownloadButton label="Download cleaned PDF"
                  onDownload={() => download(outputPdfPath(job.id, document.position), `document-${document.position}.pdf`)} />
              )}
              <Dialog.Close aria-label="Close"
                className="grid size-[34px] place-items-center rounded-[4px] border border-line text-fg-2 transition-colors hover:text-foreground">
                <X className="size-4" aria-hidden />
              </Dialog.Close>
            </div>
          </header>

          <div className="grid min-h-0 grid-cols-[1fr_1px_1fr] gap-7 px-8 pt-[22px] pb-3.5 max-[820px]:grid-cols-1 max-[820px]:grid-rows-2 max-[820px]:gap-3 max-[820px]:px-4">
            <figure className="m-0 flex min-h-0 flex-col items-center gap-3" aria-label={`Page ${current}, before`}>
              <figcaption className="label-caps">Before · builder's file</figcaption>
              <div className="min-h-0 w-full flex-1">{image("source", `Page ${current} as uploaded`)}</div>
            </figure>
            <div className="bg-line-2 max-[820px]:hidden" />
            <figure className="m-0 flex min-h-0 flex-col items-center gap-3" aria-label={`Page ${current}, after`}>
              <figcaption className="label-caps !text-fg-2">
                After{pairing.output ? ` · page ${pairing.output}` : ""}
              </figcaption>
              <div className="min-h-0 w-full flex-1">
                {!cleaned ? (
                  <Placeholder title="Not cleaned yet" />
                ) : pairing.output === null ? (
                  <Placeholder title="Dropped" detail={pairing.droppedBecause ?? undefined} />
                ) : (
                  image("output", `Page ${current} after unbranding`)
                )}
              </div>
            </figure>
          </div>

          <footer className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-[18px] border-t border-line-2 px-5 py-3.5 max-[820px]:grid-cols-1">
            <section aria-label="Changes on this page" className="flex min-w-0 flex-wrap gap-1.5 max-[820px]:max-h-[76px] max-[820px]:overflow-y-auto">
              {onPageChanges.map((item, index) => (
                <Pill key={index} number={index + 1} title={item.action.why}>{`${removalKind(item)} · ${item.action.why}`}</Pill>
              ))}
              {pairing.findings.map((finding, index) => (
                <span key={`finding-${index}`} title={finding.detail}
                  className={cn("rounded-full border px-2.5 py-0.5 text-[13px]",
                    finding.severity === "block" ? "border-danger/50 text-danger" : "border-line text-foreground")}>
                  {SEVERITY[finding.severity].label} · {CHECK[finding.check]}
                </span>
              ))}
              {onPageChanges.length === 0 && pairing.findings.length === 0 && (
                <span className="label-caps">{cleaned ? "No changes on this page" : "Not cleaned yet"}</span>
              )}
            </section>

            <div className="justify-self-center max-[820px]:order-3">
              <div className="flex items-center gap-[18px]">
                <Arrow label="Previous page" disabled={current <= 1} onClick={() => onPage(current - 1)}>
                  <ArrowLeft className="size-5" aria-hidden />
                </Arrow>
                <div className="min-w-24 text-center" aria-live="polite">
                  <span className="reading text-[20px]">{String(current).padStart(2, "0")}</span>
                  <span className="label-caps"> / {String(last).padStart(2, "0")}</span>
                  <span className="sr-only">Page {current} of {last}</span>
                </div>
                <Arrow label="Next page" disabled={current >= last} onClick={() => onPage(current + 1)}>
                  <ArrowRight className="size-5" aria-hidden />
                </Arrow>
              </div>
              {last > 1 && (
                <div className="mt-2 flex justify-center gap-[3px]" aria-hidden>
                  {Array.from({ length: last }, (_, index) => (
                    <i key={index} className={cn("h-0.5 w-1.5 bg-line",
                      pagesWithChanges.has(index + 1) && "bg-gold", index + 1 === current && "bg-foreground")} />
                  ))}
                </div>
              )}
            </div>

            {/* On a phone only the whole-document line stays, under the page's changes. */}
            <div className={cn("flex w-full min-w-0 flex-col items-end gap-1.5 max-[820px]:order-2 max-[820px]:items-start",
              !hasWholeDocument && "max-[820px]:hidden")}>
              <WholeDocument names={acrossDocument.map(describeRemoval)} findings={wholeFindings} />
              <span className="flex items-center gap-1.5 max-[820px]:hidden">
                <Key>←</Key><Key>→</Key><span className="label-caps">Pages</span>
                <Key>Esc</Key><span className="label-caps">Close</span>
              </span>
            </div>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** What applies to every page: names removed across the file, findings about the file. */
function WholeDocument({ names, findings }: { names: string[]; findings: ReturnType<typeof wholeFileFindings> }) {
  if (names.length === 0 && findings.length === 0) return null;
  return (
    <span className="block max-w-full truncate text-right text-[13px] text-fg-2 max-[820px]:text-left"
      title={[...names, ...findings.map((finding) => `${CHECK[finding.check]}: ${finding.detail}`)].join("\n")}>
      <span className="label-caps mr-2">Whole document</span>
      {[...names, ...findings.map((finding) => CHECK[finding.check])].join(" · ")}
    </span>
  );
}

function Pill({ number, title, children }: { number: number; title: string; children: string }) {
  return (
    <span title={title} className="inline-flex max-w-full items-center gap-[7px] rounded-full border border-line py-0.5 pr-2.5 pl-[3px] text-[13px] text-fg-2">
      <i className="grid size-[17px] shrink-0 place-items-center rounded-full bg-gold font-mono text-[9.5px] not-italic text-[#060607]">{number}</i>
      <span className="truncate">{children}</span>
    </span>
  );
}

function Placeholder({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="grid h-full place-items-center rounded-[2px] border border-dashed border-line p-6 text-center">
      <div className="flex flex-col gap-1.5">
        <span className="label-caps !text-fg-2">{title}</span>
        {detail && <span className="text-[14px] text-fg-3">{detail}</span>}
      </div>
    </div>
  );
}

function Arrow({ label, disabled, onClick, children }: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" aria-label={label} disabled={disabled} onClick={onClick}
      className="grid size-[46px] place-items-center rounded-full border border-line text-foreground transition-[transform,border-color] duration-300 ease-spring
        enabled:hover:scale-[1.06] enabled:hover:border-fg-3 disabled:opacity-25">
      {children}
    </button>
  );
}

function Key({ children }: { children: string }) {
  return <kbd className="min-w-5 rounded-[3px] border border-line px-[5px] py-0.5 text-center font-mono text-[11px] text-fg-2">{children}</kbd>;
}
