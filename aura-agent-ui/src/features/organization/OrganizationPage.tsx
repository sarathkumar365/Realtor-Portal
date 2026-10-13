import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, type FieldPath, useFieldArray, useForm } from "react-hook-form";
import { useBlocker } from "react-router";
import { toast } from "sonner";

import { ApiError, DEFAULT_MESSAGE } from "@/api/errors";
import type { Organization } from "@/api/organization";
import { ColourField } from "@/components/ColourField";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import { useOrganization, useSaveOrganization } from "./hooks/useOrganization";
import { MarkPreview } from "./MarkPreview";
import { type BrandForm, organizationSchema, type OrganizationForm } from "./schema";

export function OrganizationPage() {
  const organization = useOrganization();
  return (
    <>
      <PageHeader title="Organization" description="Who the agent works for, and the mark on every document." />
      {organization.isPending ? (
        <LoadingState label="Loading the profile" />
      ) : organization.isError ? (
        <ErrorState error={organization.error} onRetry={() => organization.refetch()} title="Could not load the profile" />
      ) : (
        <OrganizationEditor saved={organization.data} />
      )}
    </>
  );
}

const FONTS = ["Times", "Helvetica", "Courier"] as const;

function OrganizationEditor({ saved }: { saved: Organization }) {
  const save = useSaveOrganization();
  const form = useForm<OrganizationForm>({ resolver: zodResolver(organizationSchema), defaultValues: saved });
  const words = useFieldArray({ control: form.control, name: "brand.mark_words" });
  const [preview, setPreview] = useState<BrandForm>(saved.brand);
  const { errors, isDirty } = form.formState;

  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    isDirty && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (!isDirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty]);

  async function showPreview() {
    if (await form.trigger("brand")) setPreview(form.getValues("brand"));
  }

  function submit(values: OrganizationForm) {
    save.mutate(values, {
      onSuccess: (stored) => {
        form.reset(stored);
        setPreview(stored.brand);
        toast.success("Profile saved. Chat and new jobs use it now.");
      },
      onError: (error) => {
        if (error instanceof ApiError && error.kind === "invalid") {
          for (const [path, message] of Object.entries(error.fields)) {
            form.setError(path as FieldPath<OrganizationForm>, { message });
          }
        }
      },
    });
  }

  // A 422 that named fields is shown on them; only what has no field goes here.
  const onFields = save.error instanceof ApiError && Object.keys(save.error.fields).length > 0;
  const saveError = onFields ? null
    : save.error instanceof ApiError ? save.error.message : save.error ? DEFAULT_MESSAGE.server : null;
  const number = { valueAsNumber: true } as const;
  const brandErrors = errors.brand;

  return (
    <form noValidate onSubmit={form.handleSubmit(submit)} className="flex max-w-4xl flex-col gap-6">
      <Card className="grid gap-4 md:grid-cols-2">
        <h2 className="text-lg font-bold md:col-span-2">The brokerage</h2>
        <FormField label="Name" error={errors.name?.message}>
          <Input {...form.register("name")} />
        </FormField>
        <FormField label="Short name" hint="How the assistant refers to it in passing" error={errors.short_name?.message}>
          <Input {...form.register("short_name")} />
        </FormField>
        <FormField label="Assistant's name" error={errors.assistant_name?.message}>
          <Input {...form.register("assistant_name")} />
        </FormField>
        <FormField label="Region" error={errors.region?.message}>
          <Input {...form.register("region")} />
        </FormField>
      </Card>

      <Card className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-bold">The mark</h2>
          <p className="text-sm text-muted">Printed at the bottom of every cleaned page. One colour per word.</p>
        </div>
        <ul className="flex flex-col gap-3" aria-label="Mark words">
          {words.fields.map((field, index) => (
            <li key={field.id} className="grid grid-cols-[1fr_14rem_auto] items-end gap-3">
              <FormField label={`Word ${index + 1}`} error={brandErrors?.mark_words?.[index]?.text?.message}>
                <Input {...form.register(`brand.mark_words.${index}.text`)} />
              </FormField>
              <Controller
                control={form.control}
                name={`brand.mark_words.${index}.colour`}
                render={({ field: colour }) => (
                  <FormField label={`Colour of word ${index + 1}`} error={brandErrors?.mark_words?.[index]?.colour?.message}>
                    <ColourField value={colour.value} onChange={colour.onChange} onBlur={colour.onBlur} name={colour.name} />
                  </FormField>
                )}
              />
              <Button variant="ghost" size="icon" aria-label={`Remove word ${index + 1}`}
                disabled={words.fields.length === 1} onClick={() => words.remove(index)}>
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
        {brandErrors?.mark_words?.root?.message && (
          <p role="alert" className="text-sm text-danger">{brandErrors.mark_words.root.message}</p>
        )}
        <div>
          <Button variant="secondary" size="sm" onClick={() => words.append({ text: "", colour: "#0E1A24" })}>
            <Plus aria-hidden />Add a word
          </Button>
        </div>
        <div className="grid gap-4 md:grid-cols-5">
          <FormField label="Font" error={brandErrors?.font?.message}>
            <select className="h-10 rounded-lg border-[1.5px] border-border bg-surface px-3 text-sm" {...form.register("brand.font")}>
              {FONTS.map((font) => <option key={font}>{font}</option>)}
            </select>
          </FormField>
          <FormField label="Size (pt)" error={brandErrors?.size?.message}>
            <Input type="number" step="0.1" {...form.register("brand.size", number)} />
          </FormField>
          <FormField label="Letter spacing (pt)" error={brandErrors?.tracking?.message}>
            <Input type="number" step="0.1" {...form.register("brand.tracking", number)} />
          </FormField>
          <FormField label="Opacity (0–1)" error={brandErrors?.opacity?.message}>
            <Input type="number" step="0.05" {...form.register("brand.opacity", number)} />
          </FormField>
          <FormField label="Margin (pt)" error={brandErrors?.margin?.message}>
            <Input type="number" step="1" {...form.register("brand.margin", number)} />
          </FormField>
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Preview</h3>
            <Button variant="secondary" size="sm" onClick={showPreview}>Preview changes</Button>
          </div>
          <MarkPreview brand={preview} />
        </div>
      </Card>

      {saveError && <p role="alert" className="text-sm text-danger">{saveError}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={!isDirty || save.isPending}>{save.isPending ? "Saving" : "Save"}</Button>
        <Button variant="ghost" disabled={!isDirty || save.isPending} onClick={() => form.reset(saved)}>Discard changes</Button>
      </div>

      <ConfirmDialog
        open={blocker.state === "blocked"}
        title="Leave without saving?"
        description="Your changes to the profile will be lost."
        confirmLabel="Leave"
        cancelLabel="Stay"
        onConfirm={() => blocker.proceed?.()}
        onCancel={() => blocker.reset?.()}
      />
    </form>
  );
}
