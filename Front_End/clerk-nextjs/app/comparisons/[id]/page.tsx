import { Suspense } from "react";
import { ComparisonDetail } from "@/components/ComparisonDetail";

async function ComparisonLoader({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ComparisonDetail id={id} />;
}

export default function ComparisonPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-16 pt-4 text-zinc-100">
      <Suspense fallback={<p role="status">Loading comparison…</p>}><ComparisonLoader params={params} /></Suspense>
    </main>
  );
}
