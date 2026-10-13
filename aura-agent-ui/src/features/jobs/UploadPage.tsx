import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

import { ApiError, DEFAULT_MESSAGE } from "@/api/errors";
import { FileDropzone } from "@/components/FileDropzone";
import { FormField } from "@/components/FormField";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import type { UploadLimits } from "@/api/jobs";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { cn } from "@/lib/cn";
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

export function UploadPage() {
  const limits = useUploadLimits();
  return (
    <>
      <PageHeader title="New job" description="One project's builder PDFs, unbranded for you to review, download or file in Drive." />
      {limits.isPending ? (
        <LoadingState label="Loading the upload limits" />
      ) : limits.isError ? (
        <ErrorState error={limits.error} onRetry={() => limits.refetch()} title="Could not load the upload limits" />
      ) : (
        <UploadForm limits={limits.data} />
      )}
    </>
  );
}

function UploadForm({ limits }: { limits: UploadLimits }) {
  const navigate = useNavigate();
  const upload = useUpload();
  const [files, setFiles] = useState<File[]>([]);
  const [problems, setProblems] = useState<Record<number, string>>({});
  const [filesError, setFilesError] = useState<string | null>(null);
  const form = useForm<JobFields>({
    resolver: zodResolver(schema),
    defaultValues: { project: "", builder: "", city: "", province: "Ontario", short_forms: "", instructions: "",
      file_when_done: false },
  });
  const sending = upload.state.phase === "sending";
  const errors = form.formState.errors;

  function changeFiles(next: File[]) {
    setFiles(next);
    setProblems({});
    setFilesError(null);
  }

  async function submit(values: JobFields) {
    if (files.length === 0 || files.length > limits.max_files) {
      setFilesError(`Choose 1 to ${limits.max_files} PDFs.`);
      return;
    }
    const found: Record<number, string> = {};
    await Promise.all(files.map(async (file, index) => {
      const problem = await pdfProblem(file, limits.max_file_mb);
      if (problem) found[index] = problem;
    }));
    setProblems(found);
    if (Object.keys(found).length > 0) {
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

  return (
    <>
      <form noValidate onSubmit={form.handleSubmit(submit)} className="grid max-w-5xl gap-6 lg:grid-cols-2">
        <Card className="flex flex-col gap-4">
          <FormField label="Project" error={errors.project?.message}>
            <Input placeholder="SouthCal" {...form.register("project")} />
          </FormField>
          <FormField label="Builder" error={errors.builder?.message}>
            <Input placeholder="Arista Homes" {...form.register("builder")} />
          </FormField>
          <div className="grid grid-cols-2 gap-4">
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
          <FormField label="Instructions (optional)" hint="Anything the agent should do for this job, such as dropping a page. Its safety checks still apply."
            error={errors.instructions?.message}>
            <Textarea {...form.register("instructions")} />
          </FormField>
          <label className={cn("flex items-start gap-2 text-sm", !limits.can_file && "opacity-60")}>
            <input type="checkbox" className="mt-0.5 size-4 accent-primary" disabled={!limits.can_file}
              {...form.register("file_when_done")} />
            <span>
              <span className="font-semibold">File in Drive when done</span>
              <span className="block text-muted">
                {limits.can_file
                  ? "Off: the job waits for you to review it, download it, or file it. On: it is filed in a private Drive folder as soon as it is unbranded."
                  : "Not available: Drive is not set up on this service, or its worker is off. The cleaned PDFs can still be downloaded."}
              </span>
            </span>
          </label>
        </Card>
        <div className="flex flex-col gap-4">
          <FileDropzone label="PDFs to unbrand" files={files} onChange={changeFiles} problems={problems}
            accept={{ "application/pdf": [".pdf"] }} maxFiles={limits.max_files} disabled={sending} />
          <p className="-mt-2 text-xs text-muted">
            Up to {limits.max_file_mb} MB and {limits.max_pages} pages per file.
          </p>
          {filesError && <p role="alert" className="text-sm text-danger">{filesError}</p>}
          {failureMessage && !sending && <p role="alert" className="text-sm text-danger">{failureMessage}</p>}
          {upload.state.phase === "sending" && (
            <div className="flex flex-col gap-2">
              <Progress value={upload.state.percent} label="Upload progress" />
              <p className="text-sm text-muted">
                {upload.state.percent < 100 ? `Uploading ${upload.state.percent}%` : "Checking the files"}
              </p>
            </div>
          )}
          <div className="flex gap-2">
            <Button type="submit" disabled={sending}>{sending ? "Uploading" : "Upload and start"}</Button>
            {sending ? (
              <Button variant="secondary" onClick={upload.cancel}>Cancel upload</Button>
            ) : (
              <Button variant="ghost" asChild><Link to="/jobs">Back to jobs</Link></Button>
            )}
          </div>
        </div>
      </form>
    </>
  );
}
