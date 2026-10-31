"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { listTargets } from "@/lib/targets-service";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import { Section } from "@/components/ui/Card";
import { TargetForm } from "@/components/TargetForm";
import { TargetList } from "@/components/TargetList";

function HomeContent() {
  const toast = useToast();
  const [targets, setTargets] = useState<AnalysisTarget[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<AnalysisTarget | null>(null);

  const load = useCallback(() => {
    listTargets()
      .then((t) => {
        setTargets(t);
        setLoadError(null);
      })
      .catch(() => setLoadError("Could not load your targets. Please try again."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function handleCreated(target: AnalysisTarget) {
    setTargets((prev) => [target, ...(prev ?? [])]);
    setJustCreated(target);
    toast.success(`"${target.name}" was created.`);
  }

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 space-y-10 px-4 pb-16 pt-4 text-zinc-100">
      <Section title="Create a new target" hint="Add a business or location whose reviews you want to analyze.">
        <TargetForm onCreated={handleCreated} />
        {justCreated && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-green-800 bg-green-950/40 p-4" role="status">
            <p className="text-green-200">
              <span className="font-medium">{justCreated.name}</span> is ready. You can start ingestion from its workspace.
            </p>
            <Link
              href={`/targets/${justCreated.id}`}
              className="inline-flex h-11 items-center rounded-lg bg-violet-600 px-5 text-sm font-medium text-white hover:bg-violet-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-400"
            >
              Open workspace
            </Link>
          </div>
        )}
      </Section>

      <Section title="Your targets" hint="Select a target to open its workspace.">
        <TargetList targets={targets} error={loadError} onRetry={load} />
      </Section>
    </main>
  );
}

export default function HomePage() {
  return (
    <ToastProvider>
      <HomeContent />
    </ToastProvider>
  );
}
