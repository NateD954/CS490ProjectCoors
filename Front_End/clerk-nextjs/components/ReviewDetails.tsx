import type { PlaceSummary } from "@/lib/types";
import { Card } from "./ui/Card";

export function ReviewDetails({ place }: { place: PlaceSummary }) {
  return (
    <div className="space-y-4">
      <Card>
        <h3 className="text-lg font-semibold">{place.name}</h3>
        <p className="text-sm text-zinc-400">{place.address}</p>
        <p className="mt-3 text-zinc-200">{place.summary}</p>
        <p className="mt-3 text-sm text-zinc-300">
          {place.rating.toFixed(1)} average rating from {place.reviewCount} reviews
        </p>
        {place.topics.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {place.topics.map((t) => (
              <li key={t} className="rounded-full bg-zinc-800 px-3 py-1 text-sm text-zinc-200">
                {t}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ul className="space-y-3">
        {place.reviews.map((r) => (
          <li key={r.id}>
            <Card>
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium">{r.author}</span>
                <span className="text-sm text-zinc-400">
                  {r.rating} of 5 · {new Date(r.date).toLocaleDateString()}
                </span>
              </div>
              <p className="mt-2 text-zinc-200">{r.text}</p>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
