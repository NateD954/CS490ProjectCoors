"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { AnalysisTarget } from "@/lib/types";
import { listTargets } from "@/lib/targets-service";

// S2-017 TargetSwitcher: dropdown of your own targets. Loads them (or shows an error if the load fails)
// and opens the one you pick. The backend only returns the signed-in user's targets.
export function TargetSwitcher({ activeId }: { activeId: string }) {
  const router = useRouter();
  const [targets, setTargets] = useState<AnalysisTarget[] | null>(null);
  const [failed, setFailed] = useState(false);

  // Load the targets once when the page opens.
  useEffect(() => {
    listTargets().then(setTargets).catch(() => setFailed(true));
  }, []);

  // Show an error if loading failed, nothing while still loading.
  if (failed) return <p className="text-sm text-zinc-400">Could not load your other targets.</p>;
  if (!targets) return null;

  const activeIsKnown = targets.some((t) => t.id === activeId);

  // Go to the picked target (ignore the one that is already active).
  function handleChange(newId: string) {
    if (newId && newId !== activeId) router.push(`/targets/${newId}`);
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor="target-switcher" className="text-sm text-zinc-400">
        Active target
      </label>
      <select
        id="target-switcher"
        value={activeIsKnown ? activeId : ""}
        onChange={(e) => handleChange(e.target.value)}
        className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100"
      >
        {!activeIsKnown && <option value="">Select a target…</option>}
        {targets.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
    </div>
  );
}
