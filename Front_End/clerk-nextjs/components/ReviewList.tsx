"use client";
import { useEffect, useState } from "react";
import type { Review } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { listReviews } from "@/lib/targets-service";
import { Card } from "./ui/Card";
import { Button } from "./ui/Button";
import { Spinner } from "./ui/Spinner";
import { useToast } from "./ui/Toast";

type LoadState = "loading" | "ready" | "error";

function Stars({ rating }: { rating: number }) {
  return (
    <span className="text-amber-400" role="img" aria-label={`${rating} out of 5 stars`}>
      {"★".repeat(rating)}
      <span className="text-zinc-600">{"☆".repeat(5 - rating)}</span>
    </span>
  );
}

// Shows a target's stored reviews 5 at a time. "See more" only appears when more exist.
// The parent gives this component a new `key` to make it reload (for example after ingestion).
export function ReviewList({ targetId }: { targetId: string }) {
  const toast = useToast();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [state, setState] = useState<LoadState>("loading");
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listReviews(targetId, 0)
      .then((page) => {
        if (cancelled) return;
        setReviews(page.reviews);
        setHasMore(page.hasMore);
        setState("ready");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [targetId]);

  async function showMore() {
    setLoadingMore(true);
    try {
      const page = await listReviews(targetId, reviews.length);
      setReviews((prev) => [...prev, ...page.reviews]);
      setHasMore(page.hasMore);
    } catch {
      toast.error("Could not load more reviews. Please try again.");
    } finally {
      setLoadingMore(false);
    }
  }

  if (state === "loading") {
    return (
      <Card className="flex items-center gap-3 text-zinc-400">
        <Spinner /> Loading reviews…
      </Card>
    );
  }

  if (state === "error") {
    return (
      <Card>
        <p className="text-red-400">Could not load the reviews. Refresh the page to try again.</p>
      </Card>
    );
  }

  if (reviews.length === 0) {
    return (
      <Card>
        <p className="text-zinc-400">No reviews yet. Start ingestion to collect them.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <ul className="space-y-3">
        {reviews.map((r) => (
          <li key={r.id}>
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Stars rating={r.rating} />
                {r.date && <span className="text-sm text-zinc-400">{formatDate(r.date)}</span>}
              </div>
              <p className="mt-2 text-zinc-200">{r.text}</p>
            </Card>
          </li>
        ))}
      </ul>

      {hasMore && (
        <div className="flex justify-center">
          <Button variant="secondary" onClick={showMore} loading={loadingMore}>
            See more reviews
          </Button>
        </div>
      )}
    </div>
  );
}
