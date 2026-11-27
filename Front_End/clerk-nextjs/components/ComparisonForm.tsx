"use client";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { createComparison, type Comparison } from "@/lib/comparisons-service";
import { Card } from "./ui/Card";
import { Button } from "./ui/Button";
import { TextField } from "./ui/TextField";

export function ComparisonForm({ targets, onCreated }: { targets: AnalysisTarget[]; onCreated: (saved: Comparison) => void }) {
  const [name, setName] = useState("");
  const [targetAId, setTargetAId] = useState("");
  const [targetBId, setTargetBId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = name.trim().length > 0 && targetAId !== targetBId
    && targets.some((t) => t.id === targetAId) && targets.some((t) => t.id === targetBId);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const saved = await createComparison({ name: name.trim(), targetAId, targetBId });
      setName("");
      setTargetAId("");
      setTargetBId("");
      onCreated(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the comparison. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (targets.length < 2) {
    return <Card><p>You need at least two analysis targets to create a comparison.</p>
      <Link href="/home" className="text-violet-300 underline">Create another target</Link>
    </Card>;
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-4">
        <fieldset disabled={submitting} className="space-y-4">
          <TextField id="comparison-name" label="Comparison name" placeholder="e.g. NJIT vs Wingstop" value={name} onChange={(e) => setName(e.target.value)} />
          <div className="grid gap-4 sm:grid-cols-2">
            {(["A", "B"] as const).map((slot) => (
              <div key={slot} className="space-y-1.5">
                <label htmlFor={`comparison-target-${slot}`} className="block text-sm font-medium text-zinc-200">Target {slot}</label>
                <select
                  id={`comparison-target-${slot}`}
                  className="h-11 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-zinc-100 focus-visible:outline-violet-400"
                  value={slot === "A" ? targetAId : targetBId}
                  onChange={(e) => slot === "A" ? setTargetAId(e.target.value) : setTargetBId(e.target.value)}
                >
                  <option value="">Choose a target</option>
                  {targets.map((target) => <option key={target.id} value={target.id} disabled={target.id === (slot === "A" ? targetBId : targetAId)}>{target.name}</option>)}
                </select>
              </div>
            ))}
          </div>
          <p className="text-sm text-zinc-400">Choose two different targets. You can compare them before ingestion finishes.</p>
        </fieldset>
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <Button type="submit" disabled={!valid} loading={submitting}>Save comparison</Button>
      </form>
    </Card>
  );
}
