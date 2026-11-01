import Link from "next/link";
import type { AnalysisTarget } from "@/lib/types";
import { formatDate, formatSource } from "@/lib/format";
import { Card } from "./ui/Card";
import { Button } from "./ui/Button";
import { Spinner } from "./ui/Spinner";
import { StatusBadge } from "./ui/StatusBadge";

type Props = {
  targets: AnalysisTarget[] | null; // null = still loading
  error: string | null;
  onRetry: () => void;
};

export function TargetList({ targets, error, onRetry }: Props) {
  if (error) {
    return (
      <Card className="flex flex-col items-start gap-3">
        <p className="text-red-400">{error}</p>
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      </Card>
    );
  }

  if (targets === null) {
    return (
      <Card className="flex items-center gap-3 text-zinc-400">
        <Spinner /> Loading your targets…
      </Card>
    );
  }

  if (targets.length === 0) {
    return (
      <Card>
        <p className="text-zinc-400">You don&apos;t have any targets yet. Use the form above to create your first one.</p>
      </Card>
    );
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {targets.map((t) => (
        <li key={t.id}>
          <Link
            href={`/targets/${t.id}`}
            className="block h-full rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-zinc-100 transition-colors hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-400"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="font-medium">{t.name}</span>
              <StatusBadge status={t.ingestionStatus} />
            </div>
            <span className="mt-1 block text-sm text-zinc-300">{t.platform}</span>
            <span className="block truncate text-sm text-zinc-400">{formatSource(t.sourceUrl)}</span>
            <span className="mt-2 block text-xs text-zinc-500">Created {formatDate(t.createdAt)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
