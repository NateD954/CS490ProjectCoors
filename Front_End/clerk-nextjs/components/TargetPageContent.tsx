"use client";
import { useState } from "react";
import { TargetSwitcher } from "./TargetSwitcher";
import { TargetWorkspace } from "./TargetWorkspace";
import ReviewQA from "./ReviewQA";

// S2-017 TargetPageContent: puts the dropdown, workspace and Q&A on one page with the same active
// target. The key restarts everything when the target changes, so old answers never carry over.
export function TargetPageContent({ id }: { id: string }) {
  const [name, setName] = useState<string | undefined>();
  return (
    <div key={id} className="flex flex-col gap-8">
      <TargetSwitcher activeId={id} />
      <TargetWorkspace id={id} onLoaded={setName} />
      <ReviewQA targetId={id} targetName={name} />
    </div>
  );
}
