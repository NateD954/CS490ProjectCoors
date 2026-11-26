"use client";
import { useState } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { downloadAnalysisMarkdown } from "@/lib/targets-service";
import { Button } from "./ui/Button";
import { useToast } from "./ui/Toast";

// Downloads the whole saved analysis (details, ingestion summary and Q&A history) as a Markdown file.
export function ExportAnalysisButton({ target }: { target: AnalysisTarget }) {
  const toast = useToast();
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      await downloadAnalysisMarkdown(target);
      toast.success("Analysis downloaded.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not export the analysis. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <Button variant="secondary" onClick={handleExport} loading={exporting}>
      Download Markdown
    </Button>
  );
}
