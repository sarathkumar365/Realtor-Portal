import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { type Control, Controller, type FieldPath, useFieldArray, useForm, useWatch } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import { ApiError, DEFAULT_MESSAGE } from "@/api/errors";
import type { Organization } from "@/api/organization";
import { ColourField } from "@/components/ColourField";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { LeaveDialog } from "./components/LeaveDialog";
import { useOrganization, useSaveOrganization } from "./hooks/useOrganization";
import { useUnsavedGuard } from "./hooks/useUnsavedGuard";
import { MarkPreview } from "./MarkPreview";
import { type BrandForm, brandSchema } from "./schema";

const FONTS = ["Times", "Helvetica", "Courier"] as const;
// Long enough to finish typing a number, short enough to feel live; each preview
// is a render on the server.
const PREVIEW_AFTER_MS = 600;

export function MarkPage() {
  const organization = useOrganization();
  if (organization.isPending) return <LoadingState label="Loading the mark" />;
  if (organization.isError) {
    return <ErrorState error={organization.error} onRetry={() => organization.refetch()} title="Could not load the mark" />;
  }
  return <MarkForm saved={organization.data} />;
}

function MarkForm({ saved }: { saved: Organization }) {
  const navigate = useNavigate();
  const save = useSaveOrganization();
  const form = useForm<BrandForm>({ resolver: zodResolver(brandSchema), defaultValues: saved.brand });
  const words = useFieldArray({ control: form.control, name: "mark_words" });
  const { errors, isDirty } = form.formState;
  const guard = useUnsavedGuard(isDirty);
  const preview = useLivePreview(form.control, saved.brand);

  function submit(brand: BrandForm) {
    save.mutate({ ...saved, brand }, {
      onSuccess: () => {
        guard.allow();
        form.reset(brand);
        toast.success("Mark saved. New jobs use it now.");
        navigate("/organization");
      },
      onError: (error) => {
        if (error instanceof ApiError && error.kind === "invalid") {
          for (const [path, message] of Object.entries(error.fields)) {
            form.setError(path.replace(/^brand\./, "") as FieldPath<BrandForm>, { message });
          }
        }
      },
    });
  }

  const onFields = save.error instanceof ApiError && Object.keys(save.error.fields).length > 0;
  const saveError = onFields ? null
    : save.error instanceof ApiError ? save.error.message : save.error ? DEFAULT_MESSAGE.server : null;

  return (
    <form noValidate onSubmit={form.handleSubmit(submit)} className="flex flex-col">
      <PageHeader
        trail={[{ label: "Organization", to: "/organization" }]}
        title="Mark"
        description="Printed on every cleaned page. The preview updates as you change it; where on the page it goes is chosen for each document."
        actions={<>
          <Button variant="bare" asChild><Link to="/organization">Cancel</Link></Button>
          <Button type="submit" disabled={!isDirty || save.isPending}>{save.isPending ? "Saving" : "Save mark"}</Button>
        </>} />

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,340px)] items-start gap-7 max-[820px]:grid-cols-1">
        <figure className="m-0 flex flex-col gap-2.5 rounded-[10px] border border-line-2 bg-raise p-8" aria-label="Preview">
          <figcaption className="label-caps">Preview · corner of a page</figcaption>
          <div className="overflow-hidden rounded-[2px] bg-white">
            <MarkPreview brand={preview} />
          </div>
        </figure>

        <div className="flex flex-col gap-5">
          <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
            <legend className="label-caps mb-[7px]">Words</legend>
            <ul className="flex flex-col gap-3" aria-label="Mark words">
              {words.fields.map((field, index) => (
                <li key={field.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,9.5rem)_auto] items-end gap-2">
                  <FormField label={`Word ${index + 1}`} error={errors.mark_words?.[index]?.text?.message}>
                    <Input {...form.register(`mark_words.${index}.text`)} />
                  </FormField>
                  <Controller control={form.control} name={`mark_words.${index}.colour`}
                    render={({ field: colour }) => (
                      <FormField label={`Colour of word ${index + 1}`} error={errors.mark_words?.[index]?.colour?.message}>
                        <ColourField value={colour.value} onChange={colour.onChange} onBlur={colour.onBlur} name={colour.name} />
                      </FormField>
                    )} />
                  <Button variant="bare" size="icon" aria-label={`Remove word ${index + 1}`}
                    disabled={words.fields.length === 1} onClick={() => words.remove(index)}>
                    <X aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
            {errors.mark_words?.root?.message && (
              <p role="alert" className="m-0 text-[12.5px] text-danger">{errors.mark_words.root.message}</p>
            )}
            <Button variant="bare" size="sm" className="self-start"
              onClick={() => words.append({ text: "", colour: "#0E1A24" })}>
              <Plus aria-hidden />Add a word
            </Button>
          </fieldset>

          <FormField label="Font" error={errors.font?.message}>
            <select className="h-[38px] w-full rounded-[4px] border border-line bg-raise px-3 text-foreground focus:border-foreground focus:outline-none"
              {...form.register("font")}>
              {FONTS.map((font) => <option key={font}>{font}</option>)}
            </select>
          </FormField>
          <Slider control={form.control} name="size" label="Size (pt)" min={4} max={20} step={0.5} error={errors.size?.message} />
          <Slider control={form.control} name="tracking" label="Letter spacing (pt)" min={0} max={6} step={0.1} error={errors.tracking?.message} />
          <Slider control={form.control} name="opacity" label="Opacity (0–1)" min={0.05} max={1} step={0.05} error={errors.opacity?.message} />
          <Slider control={form.control} name="margin" label="Margin (pt)" min={0} max={96} step={1} error={errors.margin?.message} />
          {saveError && <p role="alert" className="m-0 text-[12.5px] text-danger">{saveError}</p>}
        </div>
      </div>
      <LeaveDialog blocker={guard.blocker} what="the mark" />
    </form>
  );
}

/** The brand to draw: the form's, once it has been valid and still for a moment. */
function useLivePreview(control: Control<BrandForm>, initial: BrandForm): BrandForm {
  const values = useWatch({ control });
  const [shown, setShown] = useState(initial);
  const key = JSON.stringify(values);
  useEffect(() => {
    const parsed = brandSchema.safeParse(JSON.parse(key));
    if (!parsed.success) return;
    const timer = setTimeout(() => setShown(parsed.data), PREVIEW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [key]);
  return shown;
}

/**
 * A slider for quick changes beside a box for the exact number. The box is the
 * value: a saved size beyond the slider's range is kept, not clamped to it.
 */
function Slider({ control, name, label, min, max, step, error }: {
  control: Control<BrandForm>;
  name: "size" | "tracking" | "opacity" | "margin";
  label: string;
  min: number;
  max: number;
  step: number;
  error?: string;
}) {
  return (
    <Controller control={control} name={name} render={({ field }) => {
      const set = (raw: string) => field.onChange(raw === "" ? Number.NaN : Number(raw));
      const shown = Number.isNaN(field.value) ? "" : String(field.value);
      return (
        <div className="flex flex-col gap-2">
          <FormField label={label} error={error}>
            <Input type="number" step={step} value={shown} onBlur={field.onBlur} name={field.name}
              onChange={(event) => set(event.target.value)} className="font-mono" />
          </FormField>
          <input type="range" min={min} max={max} step={step} aria-label={`${label}, slider`}
            value={Number.isNaN(field.value) ? min : Math.min(Math.max(field.value, min), max)}
            onChange={(event) => set(event.target.value)} className="w-full accent-foreground" />
        </div>
      );
    }} />
  );
}
