"use client";
import { useState, type FormEvent } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { TEAM_PLATFORM } from "@/lib/config";
import { hasErrors, validateTargetInput, type FieldErrors } from "@/lib/validation";
import { createTarget, TargetValidationError } from "@/lib/targets-service";
import { suggestNameFromUrl } from "@/lib/suggest-name";
import { Card } from "./ui/Card";
import { Button } from "./ui/Button";
import { TextField } from "./ui/TextField";
import { useToast } from "./ui/Toast";

export function TargetForm({ onCreated }: { onCreated: (target: AnalysisTarget) => void }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [nameEdited, setNameEdited] = useState(false); // S3-001: true once the user types their own name
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();

    const clientErrors = validateTargetInput({ name, sourceUrl });
    if (hasErrors(clientErrors)) {
      setErrors(clientErrors);
      toast.error("Please fix the highlighted fields and try again.");
      return;
    }

    setErrors({});
    setSubmitting(true);
    const loadingId = toast.loading("Creating your target. Please wait.");
    try {
      const target = await createTarget({ name, sourceUrl });
      setName("");
      setSourceUrl("");
      setNameEdited(false);
      onCreated(target);
    } catch (err) {
      if (err instanceof TargetValidationError) {
        setErrors(err.fieldErrors); // authoritative server-side messages
        toast.error("The server rejected some fields. See the messages below.");
      } else {
        toast.error(err instanceof Error ? err.message : "Could not create the target. Please try again.");
      }
    } finally {
      toast.dismiss(loadingId);
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} noValidate className="space-y-4">
        <TextField
          id="target-name"
          label="Business or location name"
          placeholder="e.g. Sample Coffee House"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setNameEdited(e.target.value !== ""); // clearing the box lets the link suggest a name again
          }}
          error={errors.name}
          hint={!nameEdited && name ? "Suggested from the link. Change it to any name you like." : undefined}
        />
        <TextField
          id="target-platform"
          label="Review platform"
          value={TEAM_PLATFORM.label}
          readOnly
          hint="Set by your team's configuration."
        />
        <TextField
          id="target-source"
          label="Link to the reviews"
          type="url"
          placeholder="https://www.google.com/maps/place/..."
          value={sourceUrl}
          onChange={(e) => {
            setSourceUrl(e.target.value);
            if (!nameEdited) setName(suggestNameFromUrl(e.target.value)); // S3-001: suggest, never overwrite the user's name
          }}
          error={errors.sourceUrl}
          hint={`Open the place in ${TEAM_PLATFORM.label} and copy the full URL from the address bar.`}
        />
        <Button type="submit" loading={submitting}>
          Create target
        </Button>
      </form>
    </Card>
  );
}
