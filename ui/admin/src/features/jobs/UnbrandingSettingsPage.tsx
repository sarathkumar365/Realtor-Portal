import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Reading, Readings } from "@/components/Readings";
import { StatusMark } from "@/components/StatusMark";

import { useUnbranderStatus } from "./hooks/useJobs";

const DESCRIPTION = "Current status of the Unbranding service. These values are view-only.";

/** The switches are the service's environment, so this page only shows them. */
export function UnbrandingSettingsPage() {
  const status = useUnbranderStatus();
  return (
    <>
      <PageHeader title="Unbranding" description={DESCRIPTION} />
      {status.isPending ? (
        <LoadingState label="Loading the settings" />
      ) : status.isError ? (
        <ErrorState error={status.error} onRetry={() => status.refetch()} title="Could not load the settings" />
      ) : (
        <Readings className="-mt-2">
          <Reading label="Unbranding" unit="the worker that cleans uploaded PDFs">
            <StatusMark kind={status.data.worker ? "done" : "idle"}>{status.data.worker ? "On" : "Off"}</StatusMark>
          </Reading>
          <Reading label="Test mode"
            unit={status.data.test_mode ? "filing goes to Drive's Test folder" : "filing goes to each project's folder"}>
            {/* Neither good nor bad, so no state colour: the word says it. */}
            <span className="text-[15px] tracking-[-0.01em]">{status.data.test_mode ? "On" : "Off"}</span>
          </Reading>
          <Reading label="Drive">
            <StatusMark kind={status.data.drive ? "done" : "idle"}>{status.data.drive ? "Set up" : "Not set up"}</StatusMark>
          </Reading>
          <Reading label="Filing" unit={status.data.filing_problem ?? undefined}>
            <StatusMark kind={status.data.filing_problem ? "failed" : "done"}>
              {status.data.filing_problem ? "Not possible" : "Ready"}
            </StatusMark>
          </Reading>
        </Readings>
      )}
    </>
  );
}
