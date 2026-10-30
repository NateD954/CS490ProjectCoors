// ---------------------------------------------------------------------------
// DATA LAYER: the ONLY file the UI talks to for data.
// Everything below is mock data. To go live, replace the body of each function
// and keep the signatures the same. No component needs to change.
//
// Recommended wiring: keep secrets (Supabase service key, scraper, LLM key)
// on the server by creating Next.js route handlers, then call them from here:
//   getSavedPlaces -> fetch("/api/places")                (Supabase select)
//   searchPlace    -> fetch("/api/search", { POST })      (scraper + save to Supabase)
//   askAboutPlace  -> fetch("/api/ask", { POST })         (LLM over stored reviews)
// ---------------------------------------------------------------------------
import type { PlaceSummary } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

let mockStore: PlaceSummary[] = [
  {
    id: "sample-1",
    name: "Sample Coffee House",
    address: "123 Market St, Newark, NJ",
    rating: 4.4,
    reviewCount: 218,
    summary:
      "Customers praise the espresso and relaxed seating. Complaints focus on weekend wait times.",
    topics: ["Great espresso", "Cozy seating", "Slow on weekends"],
    reviews: [
      { id: "r1", author: "Dana", rating: 5, text: "Best latte in the area.", date: "2026-09-12" },
      { id: "r2", author: "Chris", rating: 3, text: "Good coffee but a long wait on Saturday.", date: "2026-09-20" },
    ],
    searchedAt: "2026-10-20T12:00:00Z",
  },
];

export async function getSavedPlaces(): Promise<PlaceSummary[]> {
  await wait(300);
  return [...mockStore].sort((a, b) => b.searchedAt.localeCompare(a.searchedAt));
}

export async function searchPlace(query: string): Promise<PlaceSummary> {
  await wait(1500);
  const q = query.trim();
  if (!q) throw new Error("Enter a business name or location to search.");

  const place: PlaceSummary = {
    id: `mock-${q.toLowerCase().replace(/\s+/g, "-")}`,
    name: q,
    address: "Address will appear here after scraping",
    rating: 4.2,
    reviewCount: 3,
    summary: `Placeholder summary for "${q}". The LLM-generated overview will appear here.`,
    topics: ["Service", "Price", "Cleanliness"],
    reviews: [
      { id: "a", author: "Sam", rating: 5, text: "Placeholder review text.", date: "2026-10-01" },
      { id: "b", author: "Alex", rating: 4, text: "Another placeholder review.", date: "2026-10-05" },
      { id: "c", author: "Jo", rating: 2, text: "A critical placeholder review.", date: "2026-10-09" },
    ],
    searchedAt: new Date().toISOString(),
  };
  mockStore = [place, ...mockStore.filter((p) => p.id !== place.id)];
  return place;
}

export async function askAboutPlace(placeId: string, question: string): Promise<string> {
  await wait(1200);
  if (!question.trim()) throw new Error("Type a question first.");
  return `Placeholder answer about ${placeId} for: "${question}". The LLM response will appear here.`;
}
