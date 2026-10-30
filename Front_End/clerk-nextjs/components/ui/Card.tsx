import type { ReactNode } from "react";

// One consistent surface for every block on the page.
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-zinc-800 bg-zinc-900 p-5 text-zinc-100 ${className}`}>
      {children}
    </div>
  );
}

// One consistent section heading + optional hint.
export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold text-zinc-100">{title}</h2>
        {hint && <p className="text-sm text-zinc-400">{hint}</p>}
      </div>
      {children}
    </section>
  );
}
