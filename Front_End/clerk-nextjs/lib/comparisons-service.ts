import type { IngestionStatus } from "./types";

export type Comparison = {
  id: string;
  name: string;
  target_a_id: string | null;
  target_b_id: string | null;
  created_at: string;
};

export type ComparisonInput = { name: string; targetAId: string; targetBId: string };

export type ComparisonDataset =
  | { id: string | null; unavailable: true; reason: "unavailable" | "temporarily_unavailable" }
  | {
      id: string;
      unavailable: false;
      business_name: string;
      platform: string;
      source_url: string;
      review_summary: { review_count: number; average_rating: number | null };
      ingestion_status: IngestionStatus;
      ingestion_error: string | null;
      ingestion_skipped: number | null;
      sample_reviews: { id: string; rating: number; review_text: string | null; reviewed_at: string | null }[];
    };

export type ComparisonDetail = Comparison & { target_a: ComparisonDataset; target_b: ComparisonDataset };

async function request<T>(path = "", init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/backend/comparisons${path}`, {
      ...init,
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
  } catch {
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = null;
    }
    if (response.status === 401) throw new Error("Your session has expired. Please sign in again.");
    if (response.status === 403) throw new Error("You don't have access to this comparison or its targets.");
    if (response.status >= 500) throw new Error("Could not load or save the comparison. Please try again.");
    throw new Error(typeof detail === "string" ? detail : "The comparison request failed. Please try again.");
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function listComparisons(): Promise<Comparison[]> {
  return request();
}

export function getComparison(id: string): Promise<ComparisonDetail> {
  return request(`/${encodeURIComponent(id)}`);
}

export function createComparison(input: ComparisonInput): Promise<Comparison> {
  return request("", { method: "POST", body: JSON.stringify({ ...input, name: input.name.trim() }) });
}

export function deleteComparison(id: string): Promise<void> {
  return request(`/${encodeURIComponent(id)}`, { method: "DELETE" });
}
