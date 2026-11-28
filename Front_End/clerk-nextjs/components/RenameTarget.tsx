"use client";
import { useState, type FormEvent } from "react";
import { renameTarget } from "@/lib/rename-service";
import { validateName } from "@/lib/name-rules";
import { Button } from "./ui/Button";
import { TextField } from "./ui/TextField";

// S3-002 RenameTarget: shows the analysis name with a Rename button. Rename turns it into a
// small form. Saving changes only the name, then tells the page the new name.
export function RenameTarget({ id, name, onRenamed }: { id: string; name: string; onRenamed: (newName: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);

  function startEditing() {
    setValue(name);
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
    if (value.replace(/\s+/g, " ").trim() === name) {
      setEditing(false); // nothing changed, so nothing to save
      return;
    }
    setSaving(true);
    try {
      onRenamed(await renameTarget(id, value));
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename this target. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="break-words">{name}</p>
        <Button type="button" variant="secondary" onClick={startEditing} aria-label="Rename this analysis">
          Rename
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={save} noValidate className="space-y-3">
      <TextField id="rename-target" label="New name" value={value} onChange={(e) => setValue(e.target.value)} error={error} autoFocus />
      <div className="flex gap-2">
        <Button type="submit" loading={saving}>
          Save name
        </Button>
        <Button type="button" variant="secondary" onClick={() => setEditing(false)} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
