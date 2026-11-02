// UI-side view of an AnalysisTarget. The backend owns persistence and
// assigns the owner from the authenticated identity, so the UI never sends or
// edits an owner. Keep these field names in sync with the backend teammate's
// API responses (or map their response to this shape in targets-service.ts).

export type IngestionStatus = "not_started" | "in_progress" | "completed" | "failed";

export type AnalysisTarget = {
  id: string; // unique target identifier
  name: string; // entity / target name
  platform: string; // supported review platform (display label)
  sourceUrl: string; // source URL or equivalent reference
  createdAt: string; // ISO timestamp
  ingestionStatus: IngestionStatus; // basic ingestion state
  ingestionMessage?: string; // optional detail, e.g. a failure reason
};

// What the user submits. Platform and owner are NOT part of this: the platform
// is fixed by team config and the owner comes from the logged-in session.
export type NewTargetInput = {
  name: string;
  sourceUrl: string;
};

// One stored review, as shown in the workspace. The reviews table does not keep
// the reviewer's name, so only rating, text and date are available.
export type Review = {
  id: string;
  rating: number; // 1-5
  text: string;
  date: string | null; // ISO timestamp when Google gave one
};
