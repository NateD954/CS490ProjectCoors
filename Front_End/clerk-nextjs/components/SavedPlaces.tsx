import type { PlaceSummary } from "@/lib/types";
import { Card } from "./ui/Card";

type Props = {
  places: PlaceSummary[];
  selectedId?: string;
  onSelect: (place: PlaceSummary) => void;
};

export function SavedPlaces({ places, selectedId, onSelect }: Props) {
  if (places.length === 0) {
    return (
      <Card>
        <p className="text-zinc-400">No saved searches yet. Search for a business above to get started.</p>
      </Card>
    );
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {places.map((p) => {
        const active = p.id === selectedId;
        return (
          <li key={p.id}>
            <button
              onClick={() => onSelect(p)}
              aria-pressed={active}
              className={`w-full rounded-xl border p-4 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-400 ${
                active ? "border-violet-500 bg-violet-950/40 text-zinc-100" : "border-zinc-800 bg-zinc-900 text-zinc-100 hover:bg-zinc-800"
              }`}
            >
              <span className="block font-medium">{p.name}</span>
              <span className="block text-sm text-zinc-400">{p.address}</span>
              <span className="mt-1 block text-sm text-zinc-300">
                {p.rating.toFixed(1)} stars · {p.reviewCount} reviews
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
