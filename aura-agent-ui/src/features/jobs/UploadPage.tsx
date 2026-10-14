import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

import { ApiError, DEFAULT_MESSAGE } from "@/api/errors";
import type { UploadLimits } from "@/api/jobs";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import { pdfProblem } from "@/lib/pdfCheck";

import { useUploadLimits } from "./hooks/useJobs";
import { useUpload } from "./hooks/useUpload";

// Mirrors NewJob in aura-chat: project, builder and city are required.
const schema = z.object({
  project: z.string().trim().min(1, "Enter the project's name"),
  builder: z.string().trim().min(1, "Enter the builder"),
  city: z.string().trim().min(1, "Enter the city"),
  province: z.string().trim(),
  short_forms: z.string(),
  instructions: z.string(),
  file_when_done: z.boolean(),
});
type JobFields = z.infer<typeof schema>;
const FIELDS = new Set(Object.keys(schema.shape));

const TRAIL = [{ label: "Unbranding", to: "/jobs" }];

export function UploadPage() {
  const limits = useUploadLimits();
  if (limits.isPending) return <LoadingState label="Loading the upload limits" />;
  if (limits.isError) {
    return <ErrorState error={limits.error} onRetry={() => limits.refetch()} title="Could not load the upload limits" />;
  }
  return <NewJob limits={limits.data} />;
}

/**
 * Files first: the page is one upload button until PDFs are chosen, then asks
 * for the project's details. The agent cannot read those from the PDFs yet, so
 * a person types them once.
 */
function NewJob({ limits }: { limits: UploadLimits }) {
  const navigate = useNavigate();
  const upload = useUpload();
  const [files, setFiles] = useState<File[]>([]);
  const [problems, setProblems] = useState<(string | null)[]>([]);
  const [filesError, setFilesError] = useState<string | null>(null);
  const sending = upload.state.phase === "sending";
  const form = useForm<JobFields>({
    resolver: zodResolver(schema),
    defaultValues: { project: "", builder: "", city: "", province: "Ontario", short_forms: "", instructions: "",
      file_when_done: false },
  });
  const errors = form.formState.errors;
  const latest = useRef<File[]>([]);

  async function changeFiles(next: File[]) {
    latest.current = next;
    setFiles(next);
    setProblems([]);
    setFilesError(next.length > limits.max_files ? `Choose up to ${limits.max_files} PDFs.` : null);
    // Checked as they arrive, so a bad file is marked before the details are typed.
    const found = await Promise.all(next.map((file) => pdfProblem(file, limits.max_file_mb)));
    // A slower check of an earlier list must not mark the wrong files.
    if (latest.current === next) setProblems(found);
  }

  const { getRootProps, getInputProps, open, isDragActive } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    noClick: true,
    noKeyboard: true,
    disabled: sending,
    // Rejected files are kept so the page can say why; dropzone would drop them silently.
    onDrop: (accepted, rejected) => void changeFiles([...files, ...accepted, ...rejected.map((item) => item.file)]),
  });

  async function submit(values: JobFields) {
    if (files.length === 0 || files.length > limits.max_files) {
      setFilesError(`Choose 1 to ${limits.max_files} PDFs.`);
      return;
    }
    const found = await Promise.all(files.map((file) => pdfProblem(file, limits.max_file_mb)));
    setProblems(found);
    if (found.some(Boolean)) {
      setFilesError("Remove or replace the files marked in red.");
      return;
    }
    const body = new FormData();
    for (const file of files) body.append("files", file, file.name);
    for (const [name, value] of Object.entries(values)) {
      body.append(name, typeof value === "boolean" ? String(value) : value.trim());
    }
    const { accepted, error } = await upload.send(body);
    if (accepted) navigate(`/jobs/${accepted.job_id}`);
    if (error instanceof ApiError && error.kind === "invalid") {
      for (const [field, message] of Object.entries(error.fields)) {
        if (FIELDS.has(field)) form.setError(field as keyof JobFields, { message });
      }
    }
  }

  const failure = upload.state.phase === "failed" ? upload.state.error : null;
  // A 422 that named form fields is shown on them; only the rest goes here.
  const onFields = failure instanceof ApiError && Object.keys(failure.fields).some((field) => FIELDS.has(field));
  const failureMessage = onFields ? null
    : failure instanceof ApiError ? failure.message : failure ? DEFAULT_MESSAGE.server : null;
  const limitsLine = `Up to ${limits.max_files} PDFs, ${limits.max_file_mb} MB and ${limits.max_pages} pages each.`;

  return (
    <div {...getRootProps({ className: "relative flex flex-col outline-none" })}>
      <input {...getInputProps({ "aria-label": "PDFs to unbrand" })} />
      {isDragActive && (
        <div aria-hidden className="pointer-events-none absolute -inset-3 z-10 grid place-items-center rounded-[10px] border border-dashed border-fg-3 bg-raise/80">
          <span className="label-caps !text-foreground">Drop them here</span>
        </div>
      )}

      {files.length === 0 ? (
        <>
          <PageHeader trail={TRAIL} title="New job" />
          <div className="grid min-h-[calc(100vh-260px)] place-items-center text-center">
            <div className="flex flex-col items-center gap-[18px]">
              <button type="button" onClick={open} aria-label="Choose PDFs"
                className="grid size-[120px] place-items-center rounded-full border border-line text-fg-2
                  transition-[transform,color,border-color] duration-400 ease-spring hover:scale-[1.04] hover:border-fg-3 hover:text-foreground">
                <Upload className="size-[30px]" strokeWidth={1.5} aria-hidden />
              </button>
              <h2>Upload builder PDFs</h2>
              <p className="m-0 max-w-[40ch] text-[12.5px] leading-[1.7] text-fg-3">
                Choose files, or drop them anywhere on this page.<br />{limitsLine}
              </p>
            </div>
          </div>
        </>
      ) : (
        <form noValidate onSubmit={form.handleSubmit(submit)} className="flex animate-[rise_0.5s_var(--ease-spring)_both] flex-col">
          <PageHeader trail={[...TRAIL, { label: "New job", to: "/jobs/new" }]} title="About this project" />
          <div className="grid grid-cols-[minmax(0,290px)_minmax(0,1fr)] items-start gap-7 max-[820px]:grid-cols-1">
            <section aria-label="Files" className="flex flex-col gap-3">
              <div className="flex items-baseline justify-between">
                <span className="label-caps">{files.length} {files.length === 1 ? "file" : "files"}</span>
                <Button variant="bare" size="sm" onClick={open} disabled={sending}><Plus aria-hidden />Add</Button>
              </div>
              <ul className="flex flex-col border-t border-line-2">
                {files.map((file, index) => (
                  <li key={`${file.name}-${index}`}
                    className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-3 border-b border-line-2 py-[11px]">
                    <span aria-hidden className="paper-dim relative h-9 w-7 rounded-[2px] bg-white">
                      <span className="absolute inset-x-0 bottom-[3px] text-center font-mono text-[6.5px] text-[#6b7782]">PDF</span>
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[13px]">{file.name}</span>
                      <span className={cn("label-caps", problems[index] && "!text-danger")}>
                        {problems[index] ?? formatBytes(file.size)}
                      </span>
                    </span>
                    <Button variant="bare" size="icon" disabled={sending} aria-label={`Remove ${file.name}`}
                      onClick={() => void changeFiles(files.filter((_, other) => other !== index))}>
                      <X aria-hidden />
                    </Button>
                  </li>
                ))}
              </ul>
              <p className="m-0 text-[12px] text-fg-3">{limitsLine}</p>
              {filesError && <p role="alert" className="m-0 text-[12.5px] text-danger">{filesError}</p>}
            </section>

            <div className="flex flex-col gap-5">
              <p className="m-0 max-w-[62ch] border-l-2 border-line pl-3 text-[12.5px] leading-[1.7] text-fg-3">
                A later version reads these from the PDFs. For now, fill them in once.
              </p>
              <div className="grid grid-cols-2 gap-[18px] max-[820px]:grid-cols-1">
                <FormField label="Project" error={errors.project?.message}>
                  <Input placeholder="SouthCal" {...form.register("project")} />
                </FormField>
                <FormField label="Builder" error={errors.builder?.message}>
                  <Input placeholder="Arista Homes" {...form.register("builder")} />
                </FormField>
                <FormField label="City" error={errors.city?.message}>
                  <Input placeholder="Vaughan" {...form.register("city")} />
                </FormField>
                <FormField label="Province" error={errors.province?.message}>
                  <Input {...form.register("province")} />
                </FormField>
              </div>
              <FormField label="Short forms" hint="Other names the builder or project goes by, separated by commas: AH, SC"
                error={errors.short_forms?.message}>
                <Input {...form.register("short_forms")} />
              </FormField>
              <FormField label="Instructions · optional"
                hint="Anything the agent should do for this job, such as dropping a page. Its safety checks still apply."
                error={errors.instructions?.message}>
                <Textarea placeholder="For example: drop the last page of the price list." {...form.register("instructions")} />
              </FormField>
              <label className={cn("flex cursor-pointer items-start gap-[11px]", !limits.can_file && "cursor-not-allowed opacity-60")}>
                <input type="checkbox" className="mt-[3px] accent-foreground" disabled={!limits.can_file}
                  {...form.register("file_when_done")} />
                <span>
                  File in Drive when done
                  <span className="block text-[12px] text-fg-3">
                    {limits.can_file
                      ? "Off: the job waits for you to review, download or file it. On: it is filed in a private Drive folder as soon as it is unbranded."
                      : "Not available: Drive is not set up on this service, or its worker is off. The cleaned PDFs can still be downloaded."}
                  </span>
                </span>
              </label>

              {failureMessage && !sending && <p role="alert" className="m-0 text-[12.5px] text-danger">{failureMessage}</p>}
              {upload.state.phase === "sending" && (
                <div className="flex flex-col gap-2">
                  <Progress value={upload.state.percent} label="Upload progress" />
                  <span className="label-caps">
                    {upload.state.percent < 100 ? `Uploading ${upload.state.percent}%` : "Checking the files"}
                  </span>
                </div>
              )}
              <div className="flex justify-between gap-2 border-t border-line-2 pt-[18px]">
                {sending ? (
                  <Button variant="quiet" onClick={upload.cancel}>Cancel upload</Button>
                ) : (
                  <Button variant="bare" asChild><Link to="/jobs">Cancel</Link></Button>
                )}
                <Button type="submit" disabled={sending}>{sending ? "Uploading" : "Start unbranding"}</Button>
              </div>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}
