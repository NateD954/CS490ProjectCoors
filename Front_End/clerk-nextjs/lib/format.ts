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

export const formatDate = (iso: string) => new Date(iso).toLocaleDateString();
