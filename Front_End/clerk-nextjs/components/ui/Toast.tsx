"use client";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Spinner } from "./Spinner";

type Kind = "success" | "error" | "loading";
type Item = { id: number; kind: Kind; message: string };
type ToastApi = {
  success: (message: string) => void;
  error: (message: string) => void;
  loading: (message: string) => number; // returns an id, pass it to dismiss() when done
  dismiss: (id: number) => void;
};

const ToastContext = createContext<ToastApi | null>(null);
let nextId = 1;

const styles: Record<Kind, string> = {
  success: "border-green-800 bg-green-950 text-green-200",
  error: "border-red-800 bg-red-950 text-red-200",
  loading: "border-zinc-700 bg-zinc-900 text-zinc-100",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);

  const dismiss = useCallback((id: number) => setItems((p) => p.filter((t) => t.id !== id)), []);

  const push = useCallback(
    (kind: Kind, message: string, autoCloseMs?: number) => {
      const id = nextId++;
      setItems((p) => [...p, { id, kind, message }]);
      if (autoCloseMs) setTimeout(() => dismiss(id), autoCloseMs);
      return id;
    },
    [dismiss]
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => void push("success", m, 4000),
      error: (m) => void push("error", m, 7000),
      loading: (m) => push("loading", m),
      dismiss,
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`flex items-start gap-3 rounded-lg border p-3 text-sm shadow-lg shadow-black/40 ${styles[t.kind]}`}>
            {t.kind === "loading" && <Spinner className="mt-0.5 h-4 w-4 shrink-0" />}
            <span className="flex-1">{t.message}</span>
            {t.kind !== "loading" && (
              <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="text-lg leading-none opacity-60 hover:opacity-100">
                ×
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
