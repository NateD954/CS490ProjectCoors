"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { listTargets } from "@/lib/targets-service";
import { deleteComparison, listComparisons, type Comparison } from "@/lib/comparisons-service";
import { formatDate } from "@/lib/format";
import { ComparisonForm } from "./ComparisonForm";
import { Button } from "./ui/Button";
import { Card, Section } from "./ui/Card";

export function ComparisonsPageContent() {
  const router = useRouter();
  const [targets, setTargets] = useState<AnalysisTarget[] | null>(null);
  const [comparisons, setComparisons] = useState<Comparison[] | null>(null);
  const [targetsError, setTargetsError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    listTargets().then((rows) => {
      if (active) { setTargets(rows); setTargetsError(null); }
    }).catch(() => { if (active) setTargetsError("Could not load your targets. Please try again."); });
    listComparisons().then((rows) => {
      if (active) { setComparisons(rows); setListError(null); }
    }).catch((err) => { if (active) setListError(err instanceof Error ? err.message : "Could not load your comparisons."); });
    return () => { active = false; };
  }, [attempt]);

  function created(saved: Comparison) {
    setComparisons((rows) => [saved, ...(rows ?? [])]);
    router.push(`/comparisons/${saved.id}`);
  }

  async function remove(saved: Comparison) {
    if (deleting) return;
    setDeleting(saved.id);
    setDeleteError(null);
    try {
      await deleteComparison(saved.id);
      setComparisons((rows) => rows?.filter((row) => row.id !== saved.id) ?? []);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Could not delete the comparison. Please try again.");
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="space-y-8">
      <Link href="/home" className="text-violet-300 underline">Back to your targets</Link>
      <h1 className="text-2xl font-semibold">Comparisons</h1>
      <Section title="Create a comparison" hint="Save two targets together to compare their stored reviews.">
        {targetsError ? <p role="alert">{targetsError}</p> : targets === null ? <p role="status">Loading targets…</p> : <ComparisonForm targets={targets} onCreated={created} />}
      </Section>
      <Section title="Saved comparisons" hint="Reopen a comparison to see the latest stored data for each target.">
        {listError ? <p role="alert">{listError}</p> : comparisons === null ? <p role="status">Loading comparisons…</p> : comparisons.length === 0 ? <Card>No saved comparisons yet.</Card> : (
          <ul className="space-y-3">
            {comparisons.map((saved) => (
              <li key={saved.id}>
                <Card className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <Link href={`/comparisons/${saved.id}`} className="font-medium text-violet-300 underline">{saved.name}</Link>
                    <p className="text-sm text-zinc-400">Saved {formatDate(saved.created_at)}</p>
                    {(!saved.target_a_id || !saved.target_b_id) && <p className="text-sm text-amber-300">An analysis is unavailable.</p>}
                  </div>
                  <Button variant="secondary" disabled={deleting !== null} loading={deleting === saved.id} onClick={() => remove(saved)} aria-label={`Delete comparison ${saved.name}`}>Delete comparison</Button>
                </Card>
              </li>
            ))}
          </ul>
        )}
        {deleteError && <p role="alert" className="text-red-300">{deleteError}</p>}
        <p className="text-sm text-zinc-400">Deleting a comparison keeps both targets and their reviews.</p>
      </Section>
      {(targetsError || listError) && <Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Try again</Button>}
    </div>
  );
}
