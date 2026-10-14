import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { type FieldPath, useForm } from "react-hook-form";
import { Link } from "react-router";
import { toast } from "sonner";

import { ApiError, DEFAULT_MESSAGE } from "@/api/errors";
import type { Organization } from "@/api/organization";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Reading, Readings } from "@/components/Readings";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { LeaveDialog } from "./components/LeaveDialog";
import { useOrganization, useSaveOrganization } from "./hooks/useOrganization";
import { useUnsavedGuard } from "./hooks/useUnsavedGuard";
import { MarkPreview } from "./MarkPreview";
import { type DetailsForm, detailsSchema } from "./schema";

const DESCRIPTION = "Who the agent works for. It appears in answers and on every cleaned page.";

export function OrganizationPage() {
  const organization = useOrganization();
  const [editing, setEditing] = useState(false);

  if (organization.isPending || organization.isError) {
    return (
      <>
        <PageHeader title="Organization" description={DESCRIPTION} />
        {organization.isPending
          ? <LoadingState label="Loading the profile" />
          : <ErrorState error={organization.error} onRetry={() => organization.refetch()} title="Could not load the profile" />}
      </>
    );
  }
  const saved = organization.data;

  return (
    <div className="flex flex-col gap-[34px]">
      {editing ? (
        <DetailsEditor saved={saved} onDone={() => setEditing(false)} />
      ) : (
        <>
          <PageHeader title="Organization" description={DESCRIPTION}
            actions={<Button variant="quiet" onClick={() => setEditing(true)}>Edit</Button>} />
          <Readings className="-mt-2 grid-cols-[repeat(auto-fit,minmax(min(220px,calc(50%_-_1px)),1fr))]">
            <Fact label="Name" value={saved.name} />
            <Fact label="Short name" value={saved.short_name} />
            <Fact label="Assistant" value={saved.assistant_name} />
            <Fact label="Region" value={saved.region} />
          </Readings>
        </>
      )}

      <Section title="Branding">
        <Link to="/settings/organization/mark"
          className="group grid grid-cols-[150px_minmax(0,1fr)_auto] items-center gap-5 rounded-[10px] border border-line-2 bg-raise p-3.5
            transition-colors duration-300 hover:border-line max-[820px]:grid-cols-[96px_minmax(0,1fr)]">
          <div className="paper-dim overflow-hidden rounded-[4px] bg-white group-hover:opacity-100">
            <MarkPreview brand={saved.brand} compact />
          </div>
          <span className="min-w-0">
            <span className="block text-[15px] tracking-[-0.015em]">Mark</span>
            <span className="block text-[13px] text-fg-2">
              The words placed on each cleaned page, with their colour, size and spacing.
            </span>
          </span>
          <span className="label-caps flex items-center gap-1.5 transition-colors group-hover:text-foreground max-[820px]:hidden">
            Edit <ArrowRight className="size-3.5" aria-hidden />
          </span>
        </Link>
      </Section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <Reading label={label}><span className="text-[15px] tracking-[-0.01em]">{value}</span></Reading>;
}

/** The brokerage's details. The server takes the whole profile, so the saved
 * mark goes back with them unchanged. */
function DetailsEditor({ saved, onDone }: { saved: Organization; onDone: () => void }) {
  const save = useSaveOrganization();
  const form = useForm<DetailsForm>({ resolver: zodResolver(detailsSchema), defaultValues: saved });
  const { errors, isDirty } = form.formState;
  const guard = useUnsavedGuard(isDirty);

  function submit(values: DetailsForm) {
    save.mutate({ ...saved, ...values }, {
      onSuccess: () => {
        form.reset(values);
        toast.success("Profile saved. Chat and new jobs use it now.");
        onDone();
      },
      onError: (error) => {
        if (error instanceof ApiError && error.kind === "invalid") {
          for (const [path, message] of Object.entries(error.fields)) {
            form.setError(path as FieldPath<DetailsForm>, { message });
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
      <PageHeader title="Organization" description={DESCRIPTION}
        actions={<>
          <Button variant="bare" disabled={save.isPending} onClick={() => { form.reset(saved); onDone(); }}>Cancel</Button>
          <Button type="submit" disabled={!isDirty || save.isPending}>{save.isPending ? "Saving" : "Save"}</Button>
        </>} />
      <div className="grid max-w-3xl grid-cols-2 gap-[18px] max-[820px]:grid-cols-1">
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
      </div>
      {saveError && <p role="alert" className="mt-4 text-[13px] text-danger">{saveError}</p>}
      <LeaveDialog blocker={guard.blocker} what="the profile" />
    </form>
  );
}
