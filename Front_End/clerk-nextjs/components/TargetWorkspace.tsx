"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { getTarget, startIngestion } from "@/lib/targets-service";
import { Card, Section } from "./ui/Card";
import { Button } from "./ui/Button";
import { Spinner } from "./ui/Spinner";
import { StatusBadge } from "./ui/StatusBadge";
import { ReviewList } from "./ReviewList";
import { useToast } from "./ui/Toast";

type LoadState = "loading" | "ready" | "missing" | "error";

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-zinc-400">{label}</dt>
      <dd className="mt-0.5 break-words text-zinc-100">{children}</dd>
    </div>
  );
}

export function TargetWorkspace({ id }: { id: string }) {
  const toast = useToast();
  const [target, setTarget] = useState<AnalysisTarget | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [starting, setStarting] = useState(false);
  const [ingestionRuns, setIngestionRuns] = useState(0);

  const load = useCallback(() => {
    getTarget(id)
      .then((t) => {
        setTarget(t);
        setState(t ? "ready" : "missing");
      })
      .catch(() => setState("error"));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // While ingestion runs, check for a status change every few seconds.
  const inProgress = target?.ingestionStatus === "in_progress";
  useEffect(() => {
    if (!inProgress) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [inProgress, load]);

  async function handleStart() {
    if (!target) return;
    setStarting(true);
    const loadingId = toast.loading("Starting ingestion. Please wait.");
    try {
      setTarget(await startIngestion(target.id));
      setIngestionRuns((n) => n + 1);
      toast.success("Ingestion started. This page updates when it finishes.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start ingestion. Please try again.");
    } finally {
      toast.dismiss(loadingId);
      setStarting(false);
    }
  }

  const back = (
    <Link href="/home" className="text-sm text-violet-400 hover:text-violet-300">
      ← Back to all targets
    </Link>
  );

  if (state === "loading") {
    return (
      <div className="space-y-4">
        {back}
        <Card className="flex items-center gap-3 text-zinc-400">
          <Spinner /> Loading workspace…
        </Card>
      </div>
    );
  }

  if (state === "missing" || state === "error" || !target) {
    return (
      <div className="space-y-4">
        {back}
        <Card className="flex flex-col items-start gap-3">
          <p className={state === "error" ? "text-red-400" : "text-zinc-300"}>
            {state === "error" ? "Could not load this target. Please try again." : "This target was not found. It may have been removed."}
          </p>
          {state === "error" && (
            <Button variant="secondary" onClick={load}>
              Try again
            </Button>
          )}
        </Card>
      </div>
    );
  }

  const label =
    target.ingestionStatus === "not_started"
      ? "Start ingestion"
      : target.ingestionStatus === "in_progress"
        ? "Ingestion in progress"
        : "Run ingestion again";

  return (
    <div className="space-y-8">
      {back}

      <Section title={target.name} hint="Workspace for this analysis target.">
        <Card>
          <dl className="grid gap-4 sm:grid-cols-2">
            <Detail label="Target name">{target.name}</Detail>
            <Detail label="Review platform">{target.platform}</Detail>
            <Detail label="Source">
              <a href={target.sourceUrl} target="_blank" rel="noopener noreferrer" className="text-violet-400 underline hover:text-violet-300">
                {target.sourceUrl}
              </a>
            </Detail>
            <Detail label="Created">{formatDate(target.createdAt)}</Detail>
          </dl>
        </Card>
      </Section>

      <Section title="Ingestion" hint="Collect the reviews for this target so they can be analyzed.">
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-zinc-400">Current state</span>
            <StatusBadge status={target.ingestionStatus} />
          </div>
          {target.ingestionStatus === "failed" && (
            <p className="text-sm text-red-400">{target.ingestionMessage ?? "Ingestion failed. You can try again."}</p>
          )}
          <Button onClick={handleStart} loading={starting || inProgress} disabled={inProgress}>
            {label}
          </Button>
        </Card>
      </Section>

      <Section title="Reviews" hint="Newest first.">
        {/* The key makes the list reload whenever ingestion runs or its state changes. */}
        <ReviewList key={`${target.ingestionStatus}-${ingestionRuns}`} targetId={target.id} />
      </Section>

      <Section title="Summary and questions">
        <div className="rounded-xl border border-dashed border-zinc-700 p-5 text-zinc-400">
          The ingestion summary and question-and-answer tools will appear here in a later sprint.
        </div>
      </Section>
    </div>
  );
}
