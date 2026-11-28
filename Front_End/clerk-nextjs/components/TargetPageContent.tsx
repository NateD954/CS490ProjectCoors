"use client";
import { useState } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { qaBlockedReason } from "@/lib/qa-state";
import { TargetSwitcher } from "./TargetSwitcher";
import { TargetWorkspace } from "./TargetWorkspace";
import ReviewQA from "./ReviewQA";

// S2-017 TargetPageContent: puts the dropdown, workspace and Q&A on one page with the same active
// target. S2-019: the key gives each target its own fresh copy of the page, including the saved
// name, so nothing from the old target (or a late response for it) can show up under the new one.
export function TargetPageContent({ id }: { id: string }) {
  return <TargetPage key={id} id={id} />;
}

function TargetPage({ id }: { id: string }) {
  const [target, setTarget] = useState<AnalysisTarget | undefined>();
  return (
    <div className="flex flex-col gap-8">
      <TargetSwitcher activeId={id} activeName={target?.name} />
      <TargetWorkspace id={id} onLoaded={setTarget} />
      <ReviewQA targetId={id} targetName={target?.name} blockedReason={qaBlockedReason(target)} />
    </div>
  );
}
