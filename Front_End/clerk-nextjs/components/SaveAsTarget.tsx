"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { saveTargetAs, suggestCopyName } from "@/lib/save-as-service";
import { validateName } from "@/lib/name-rules";
import { Button } from "./ui/Button";
import { TextField } from "./ui/TextField";

// S3-003 SaveAsTarget: "Save a copy" turns into a small form. Saving makes a separate analysis
// with its own copy of the reviews, then opens it. The original is left exactly as it was.
export function SaveAsTarget({ id, name }: { id: string; name: string }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);

  function startEditing() {
    setValue(suggestCopyName(name));
    setError(undefined);
    setEditing(true);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    const problem = validateName(value);
    if (problem) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError(undefined);
    try {
      const copy = await saveTargetAs(id, value);
      router.push(`/targets/${copy.id}`); // the page for the copy loads on its own
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the copy. Please try again.");
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <Button type="button" variant="secondary" onClick={startEditing} aria-label="Save a copy of this analysis">
        Save a copy
      </Button>
    );
  }

  return (
    <form onSubmit={save} noValidate className="space-y-3">
      <TextField id="save-as-name" label="Name for the copy" value={value} onChange={(e) => setValue(e.target.value)} error={error} autoFocus />
      <p className="text-sm text-zinc-400">
        The copy gets its own saved reviews. Questions and answers are not copied, so it starts with an empty history.
      </p>
      <div className="flex gap-2">
        <Button type="submit" loading={saving}>
          Save copy
        </Button>
        <Button type="button" variant="secondary" onClick={() => setEditing(false)} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
