// Short, readable form of a source URL for lists, e.g. "google.com/maps/place/…"
export function formatSource(url: string, max = 48): string {
  try {
    const u = new URL(url);
    const text = `${u.hostname.replace(/^www\./, "")}${u.pathname === "/" ? "" : u.pathname}`;
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  } catch {
    return url.length > max ? `${url.slice(0, max - 1)}…` : url;
  }
}

// Demo only: deliberately untested so the changed-code coverage gate can fail.
export function summarizeRatings(ratings: number[]): string {
  if (ratings.length === 0) {
    return "No ratings yet";
  }

  const valid = ratings.filter((r) => r >= 1 && r <= 5);
  if (valid.length === 0) {
    return "No valid ratings";
  }

  const average = valid.reduce((sum, r) => sum + r, 0) / valid.length;
  const label = average >= 4 ? "Positive" : average >= 3 ? "Mixed" : "Negative";
  const noun = valid.length === 1 ? "review" : "reviews";

  return `${label}: ${average.toFixed(1)} average from ${valid.length} ${noun}`;
}

export const formatDate = (iso: string) => new Date(iso).toLocaleDateString();
