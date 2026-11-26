"use client";
import { useState } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { downloadReviewsCsv } from "@/lib/targets-service";
import { Button } from "./ui/Button";
import { useToast } from "./ui/Toast";

// Downloads the target's stored reviews as a CSV file. It is switched off while the
// target is known to have no stored reviews, because there would be nothing to export.
export function ExportReviewsButton({ target }: { target: AnalysisTarget }) {
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const empty = target.reviewSummary?.count === 0;

  async function handleExport() {
    setExporting(true);
    try {
      await downloadReviewsCsv(target);
      toast.success("Reviews downloaded.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not export the reviews. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="secondary" onClick={handleExport} loading={exporting} disabled={empty}>
        Download CSV
      </Button>
      {empty && <p className="text-sm text-zinc-400">No reviews to export yet.</p>}
    </div>
  );
}
