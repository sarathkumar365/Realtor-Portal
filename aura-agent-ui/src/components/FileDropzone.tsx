import { FileText, Upload, X } from "lucide-react";
import { useDropzone } from "react-dropzone";

import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/cn";

/** Drop or pick files; lists them with their size, a remove button and, from
 * `problems` (by index), why one cannot be sent. Checking is the caller's job. */
export function FileDropzone({ files, onChange, problems = {}, accept, maxFiles, disabled, label }: {
  files: File[];
  onChange: (files: File[]) => void;
  problems?: Record<number, string>;
  accept: Record<string, string[]>;
  maxFiles: number;
  disabled?: boolean;
  label: string;
}) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept,
    disabled,
    multiple: true,
    // The caller decides what is too many and says so; dropzone would drop them silently.
    onDrop: (accepted, rejected) => onChange([...files, ...accepted, ...rejected.map((item) => item.file)]),
  });

  return (
    <div className="flex flex-col gap-3">
      <div
        {...getRootProps({
          className: cn(
            "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-surface p-8 text-center",
            isDragActive && "border-primary bg-primary/5",
            disabled && "cursor-not-allowed opacity-50",
          ),
        })}
      >
        <input {...getInputProps({ "aria-label": label })} />
        <Upload className="size-6 text-muted" aria-hidden />
        <p className="text-sm font-semibold">{isDragActive ? "Drop them here" : "Drop PDFs here, or click to choose"}</p>
        <p className="text-xs text-muted">Up to {maxFiles} files</p>
      </div>
      {files.length > 0 && (
        <ul className="flex flex-col gap-2">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`}
              className={cn("flex items-center gap-3 rounded-lg border bg-surface px-3 py-2 text-sm",
                problems[index] ? "border-danger" : "border-border")}>
              <FileText className="size-4 shrink-0 text-muted" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{file.name}</span>
              <span className="text-xs text-muted">{formatBytes(file.size)}</span>
              {problems[index] && <span className="text-xs text-danger">{problems[index]}</span>}
              <Button variant="ghost" size="icon" disabled={disabled} aria-label={`Remove ${file.name}`}
                onClick={() => onChange(files.filter((_, other) => other !== index))}>
                <X aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
