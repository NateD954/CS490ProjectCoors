"use client";
import { useEffect, useRef, useState } from "react";
import type { PlaceSummary } from "@/lib/types";
import { getSavedPlaces, searchPlace } from "@/lib/reviews-service";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import { Section } from "@/components/ui/Card";
import { SearchBar } from "@/components/SearchBar";
import { SavedPlaces } from "@/components/SavedPlaces";
import { ReviewDetails } from "@/components/ReviewDetails";
import { AskPanel } from "@/components/AskPanel";

function HomeContent() {
  const toast = useToast();
  const [saved, setSaved] = useState<PlaceSummary[]>([]);
  const [selected, setSelected] = useState<PlaceSummary | null>(null);
  const [searching, setSearching] = useState(false);
  const detailsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getSavedPlaces()
      .then(setSaved)
      .catch(() => toast.error("Could not load your saved searches. Refresh the page to try again."));
  }, [toast]);

  function showDetails(place: PlaceSummary) {
    setSelected(place);
    setTimeout(() => detailsRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function handleSearch(query: string) {
    setSearching(true);
    const loadingId = toast.loading("Searching for reviews. Please wait.");
    try {
      const place = await searchPlace(query);
      setSaved((prev) => [place, ...prev.filter((p) => p.id !== place.id)]);
      toast.success(`Reviews loaded for ${place.name}.`);
      showDetails(place);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Search failed. Check the name and try again.");
    } finally {
      toast.dismiss(loadingId);
      setSearching(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 space-y-10 px-4 pb-16 pt-4 text-slate-900">
      <Section title="Search reviews" hint="Find a business or location to summarize its Google reviews.">
        <SearchBar onSearch={handleSearch} loading={searching} />
      </Section>

      <Section title="Saved and recent searches" hint="Select one to view its reviews and ask more questions.">
        <SavedPlaces places={saved} selectedId={selected?.id} onSelect={showDetails} />
      </Section>

      {selected && (
        <>
          <div ref={detailsRef} className="scroll-mt-4">
            <Section title={`Reviews for ${selected.name}`}>
              <ReviewDetails place={selected} />
            </Section>
          </div>

          <Section title="Ask about these reviews">
            <AskPanel key={selected.id} placeId={selected.id} placeName={selected.name} />
          </Section>
        </>
      )}
    </main>
  );
}

export default function HomePage() {
  return (
    <ToastProvider>
      <HomeContent />
    </ToastProvider>
  );
}
