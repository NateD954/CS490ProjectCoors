// Shared shapes. When Supabase is added, make your table columns match these
// (or map the rows to these shapes inside lib/reviews-service.ts).

export type ReviewItem = {
  id: string;
  author: string;
  rating: number; // 1-5
  text: string;
  date: string; // ISO string
};

export type PlaceSummary = {
  id: string;
  name: string;
  address: string;
  rating: number; // average, 1-5
  reviewCount: number;
  summary: string; // LLM-written overview
  topics: string[]; // common themes, e.g. "Friendly staff"
  reviews: ReviewItem[];
  searchedAt: string; // ISO string, used for "recent" ordering
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};
