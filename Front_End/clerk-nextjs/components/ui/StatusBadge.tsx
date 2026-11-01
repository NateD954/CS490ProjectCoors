import type { IngestionStatus } from "@/lib/types";

const styles: Record<IngestionStatus, { label: string; classes: string }> = {
  not_started: { label: "Not started", classes: "bg-zinc-800 text-zinc-300" },
  in_progress: { label: "In progress", classes: "bg-amber-950 text-amber-300" },
  completed: { label: "Completed", classes: "bg-green-950 text-green-300" },
  failed: { label: "Failed", classes: "bg-red-950 text-red-300" },
};

export function StatusBadge({ status }: { status: IngestionStatus }) {
  const s = styles[status];
  return <span className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${s.classes}`}>{s.label}</span>;
}
