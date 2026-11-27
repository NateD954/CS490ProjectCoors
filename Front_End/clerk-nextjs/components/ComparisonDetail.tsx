"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { deleteComparison, getComparison, type ComparisonDataset, type ComparisonDetail as Detail } from "@/lib/comparisons-service";
import { PLATFORM_LABELS } from "@/lib/config";
import { formatDate } from "@/lib/format";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { StatusBadge } from "./ui/StatusBadge";

function Dataset({ label, dataset }: { label: string; dataset: ComparisonDataset }) {
  return (
    <Card className="space-y-4">
      <h2 className="text-lg font-semibold">{label}</h2>
      {dataset.unavailable ? (
        <p className="text-amber-300">{dataset.reason === "temporarily_unavailable"
          ? "This analysis could not be loaded right now. Try loading the comparison again."
          : "This analysis is unavailable. It may have been deleted or you may no longer have access."}</p>
      ) : (
        <>
          <div>
            <h3 className="text-xl font-semibold">{dataset.business_name}</h3>
            <p className="text-zinc-400">{PLATFORM_LABELS[dataset.platform] ?? dataset.platform}</p>
            <a href={dataset.source_url} target="_blank" rel="noreferrer" className="text-violet-300 underline">Source reviews</a>
          </div>
          <dl className="grid grid-cols-2 gap-4">
            <div><dt className="text-sm text-zinc-400">Stored reviews</dt><dd className="text-xl">{dataset.review_summary.review_count}</dd></div>
            <div><dt className="text-sm text-zinc-400">Average rating</dt><dd className="text-xl">{dataset.review_summary.average_rating === null ? "No ratings yet" : `${Number(dataset.review_summary.average_rating).toFixed(2)} / 5`}</dd></div>
            <div><dt className="mb-1 text-sm text-zinc-400">Ingestion status</dt><dd><StatusBadge status={dataset.ingestion_status} /></dd></div>
            <div><dt className="text-sm text-zinc-400">Skipped in latest attempt</dt><dd>{dataset.ingestion_skipped ?? "—"}</dd></div>
          </dl>
          {dataset.ingestion_error && <p className="text-sm text-amber-300">{dataset.ingestion_error}</p>}
          <div className="space-y-2">
            <h3 className="font-medium">Recent reviews</h3>
            <p className="text-sm text-zinc-400">Up to three recent stored reviews.</p>
            {dataset.sample_reviews.length === 0 ? <p>No stored reviews yet.</p> : (
              <ul className="space-y-3">
                {dataset.sample_reviews.map((review) => <li key={review.id} className="space-y-1 rounded-lg border border-zinc-800 p-3">
                  <p className="text-sm text-zinc-400">{review.rating} / 5{review.reviewed_at ? ` · ${formatDate(review.reviewed_at)}` : ""}</p>
                  <p className="whitespace-pre-wrap break-words">{review.review_text || "No written review."}</p>
                </li>)}
              </ul>
            )}
          </div>
          <Link href={`/targets/${dataset.id}`} className="inline-block text-violet-300 underline">Open {dataset.business_name} workspace</Link>
        </>
      )}
    </Card>
  );
}

export function ComparisonDetail({ id }: { id: string }) {
  return <ComparisonContent key={id} id={id} />;
}

function ComparisonContent({ id }: { id: string }) {
  const router = useRouter();
  const [comparison, setComparison] = useState<Detail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    getComparison(id).then((saved) => {
      if (active) { setComparison(saved); setLoadError(null); }
    }).catch((err) => { if (active) setLoadError(err instanceof Error ? err.message : "Could not load the comparison."); });
    return () => { active = false; };
  }, [id, attempt]);

  async function remove() {
    if (deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteComparison(id);
      router.push("/comparisons");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Could not delete the comparison. Please try again.");
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link href="/comparisons" className="text-violet-300 underline">Back to saved comparisons</Link>
      {loadError ? <div className="space-y-3"><p role="alert" className="text-red-300">{loadError}</p><Button onClick={() => setAttempt((value) => value + 1)}>Try again</Button></div> : comparison === null ? <p role="status">Loading comparison…</p> : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div><h1 className="text-2xl font-semibold break-words">{comparison.name}</h1><p className="text-sm text-zinc-400">Saved {formatDate(comparison.created_at)}</p></div>
            <Button variant="secondary" loading={deleting} onClick={remove}>Delete comparison</Button>
          </div>
          <p className="text-sm text-zinc-400">Metrics come from the latest stored reviews. Deleting this comparison keeps both targets and their reviews.</p>
          {(comparison.target_a.unavailable || comparison.target_b.unavailable) && <p role="alert" className="rounded-xl border border-amber-800 bg-amber-950/30 p-4 text-amber-200">One or both analyses are unavailable. Any available dataset is still shown below.</p>}
          {deleteError && <p role="alert" className="text-red-300">{deleteError}</p>}
          <div className="grid gap-5 md:grid-cols-2"><Dataset label="Target A" dataset={comparison.target_a} /><Dataset label="Target B" dataset={comparison.target_b} /></div>
          <Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Reload comparison</Button>
        </>
      )}
    </div>
  );
}
