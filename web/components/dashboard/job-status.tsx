import { useEffect, useEffectEvent, useState } from "react";
import { formatDateTime } from "@/lib/formatters";

type JobStage = {
  name: string;
  status: "running" | "completed" | "failed" | "interrupted";
  started_at: string;
  duration_seconds: number | null;
};

type JobSnapshot = {
  status: "queued" | "running" | "completed" | "failed";
  requested_at: string | null;
  prediction_id: string | null;
  error_message: string | null;
  worker_unresponsive: boolean | null;
  queue_wait_seconds: number | null;
  processing_seconds: number | null;
  stages: JobStage[];
  warnings: string[];
  reused_prediction: boolean;
};

const stageLabels: Record<string, string> = {
  prepare: "Prepare job",
  magnetogram: "Download and convert magnetogram",
  full_disk: "Run full disk forecast",
  attribution: "Generate attribution and candidates",
  regions: "Crop and score regions",
  upload: "Upload artifacts",
  save: "Save prediction"
};

function duration(seconds: number) {
  const wholeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(wholeSeconds / 60);
  return minutes ? `${minutes}m ${wholeSeconds % 60}s` : `${wholeSeconds}s`;
}

export function JobStatusPanel({
  jobId,
  enabled,
  onCompleted,
  onOpen,
  onDismiss
}: {
  jobId: string;
  enabled: boolean;
  onCompleted: (jobId: string, predictionId: string) => void;
  onOpen: (predictionId: string) => void;
  onDismiss: () => void;
}) {
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [connection, setConnection] = useState<"retrying" | "missing" | null>(null);
  const complete = useEffectEvent((predictionId: string) => onCompleted(jobId, predictionId));
  const terminal = job?.status === "completed" || job?.status === "failed" || connection === "missing";

  useEffect(() => {
    if (!enabled || terminal) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let delay = 5000;

    async function poll() {
      try {
        const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
          cache: "no-store",
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)])
        });
        if (controller.signal.aborted) return;
        if (response.status === 404) {
          setConnection("missing");
          return;
        }
        if (!response.ok) throw new Error("Job status request failed");
        const snapshot: JobSnapshot = await response.json();
        if (controller.signal.aborted) return;
        setJob(snapshot);
        setConnection(null);
        if (snapshot.status === "completed") {
          if (snapshot.prediction_id) complete(snapshot.prediction_id);
          return;
        }
        if (snapshot.status === "failed") return;
        delay = 5000;
      } catch {
        if (controller.signal.aborted) return;
        setConnection("retrying");
        delay = Math.min(delay * 2, 30000);
      }
      timer = setTimeout(poll, delay);
    }

    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [enabled, jobId, terminal]);

  const stages = job?.stages ?? [];
  const stage = stages.at(-1);
  const predictionId = job?.prediction_id;
  let status = "Checking prediction job";
  let description: string | undefined;
  if (job?.status === "queued") {
    status = "Queued";
    if (job.queue_wait_seconds != null) description = `Waiting for a worker · ${duration(job.queue_wait_seconds)}`;
  } else if (job?.status === "running") {
    status = job.worker_unresponsive ? "Worker unresponsive" : "Running";
    if (stage?.status === "running") {
      const seconds = stage.duration_seconds ?? (Date.now() - Date.parse(stage.started_at)) / 1000;
      description = `${stageLabels[stage.name] ?? stage.name} · ${duration(seconds)}`;
    } else if (job.processing_seconds != null) {
      description = `Processing · ${duration(job.processing_seconds)}`;
    }
  } else if (job?.status === "completed") {
    status = "Completed";
    if (job.reused_prediction) description = "Used an existing prediction.";
    else if (job.processing_seconds != null) description = `Processed in ${duration(job.processing_seconds)}`;
  } else if (job?.status === "failed") {
    status = "Failed";
    description = [stage && (stageLabels[stage.name] ?? stage.name), job.error_message]
      .filter(Boolean).join(" · ");
  }

  return (
    <section className="jobStatus" aria-label="Prediction job">
      <div className="jobStatusContent">
        <div role="status">
          <strong>{connection === "missing" ? "Prediction job unavailable" : status}</strong>
          {job?.requested_at && <span> · {formatDateTime(job.requested_at)}</span>}
        </div>
        {description && <p>{description}</p>}
        {connection === "retrying" && <p role="status">Status connection lost. Retrying automatically.</p>}
        {job?.warnings?.map((warning) => <p key={warning}>{warning}</p>)}
        {stages.length > 0 && (
          <details>
            <summary>Stage timings</summary>
            <ol>
              {stages.map((item) => (
                <li key={item.name}>
                  {stageLabels[item.name] ?? item.name}
                  {item.status === "failed" && " · Failed"}
                  {item.status === "interrupted" && " · Interrupted"}
                  {item.duration_seconds != null && ` · ${duration(item.duration_seconds)}`}
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
      <div className="jobStatusActions">
        {predictionId && <button type="button" onClick={() => onOpen(predictionId)}>Open prediction</button>}
        <button type="button" onClick={onDismiss}>Dismiss</button>
      </div>
    </section>
  );
}
