"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { formatDate } from "@/lib/format";
import { Stars } from "./ReviewList";

// S3-013: a stored review that backs an answer. The backend reads these from the
// active target's reviews, so the text and rating are never written by the AI.
export interface SupportingReview {
  id: string;
  rating: number;
  review_text: string;
  reviewed_at: string | null;
}

export interface QAHistoryEntry {
  id?: string;
  question: string;
  answer: string;
  created_at?: string;
  supporting_reviews?: SupportingReview[];
}

const MAX_SUPPORTING_REVIEWS = 5;

export default function ReviewQA({
  targetId,
  targetName,
  blockedReason,
}: {
  targetId: string;
  targetName?: string;
  blockedReason?: string; // S2-020: set when the target has no reviews to ask about
}) {
  const { getToken } = useAuth();
  const [question, setQuestion] = useState("");
  const [historyState, setHistoryState] = useState<{
    targetId: string;
    entries: QAHistoryEntry[];
  }>({ targetId, entries: [] });
  const [loading, setLoading] = useState(false);
  const [loadedTargetId, setLoadedTargetId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [errorState, setErrorState] = useState<{ targetId: string; message: string }>({
    targetId,
    message: "",
  });

  const history = historyState.targetId === targetId ? historyState.entries : [];
  const error = errorState.targetId === targetId ? errorState.message : "";
  const historyLoading = loadedTargetId !== targetId;

  // S3-007: Restore persisted Q&A history when opening or switching targets
  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const token = await getToken();
        const response = await fetch(`/api/backend/targets/${targetId}/history`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response?.ok) return;
        const data = await response.json();
        if (active && Array.isArray(data)) {
          setHistoryState({ targetId, entries: data });
        }
      } catch {
        // Ignore history fetch errors so user can still ask new questions
      } finally {
        if (active) setLoadedTargetId(targetId);
      }
    })();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetId]);

  const handleAskQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedQuestion = question.trim();
    if (blockedReason || !trimmedQuestion) return;

    setLoading(true);
    setErrorState({ targetId, message: "" });

    try {
      const token = await getToken();

      const response = await fetch(`/api/backend/targets/${targetId}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question }),
      });

      if (!response.ok) {
        throw new Error("Failed to get an answer. Please try again.");
      }

      const data = await response.json();
      setHistoryState((prev) => ({
        targetId,
        entries: [
          ...(prev.targetId === targetId ? prev.entries : []),
          {
            id: data.id,
            question: data.question ?? trimmedQuestion,
            answer: data.answer,
            created_at: data.created_at,
            supporting_reviews: data.supporting_reviews,
          },
        ],
      }));
      setQuestion("");
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorState({ targetId, message: err.message });
      } else {
        setErrorState({ targetId, message: String(err) });
      }
    } finally {
      setLoading(false);
    }
  };

  // S3-008: Clear Q&A history for the active target without deleting target or reviews
  const handleClearHistory = async () => {
    if (clearing || history.length === 0) return;

    setClearing(true);
    setErrorState({ targetId, message: "" });

    try {
      const token = await getToken();
      const response = await fetch(`/api/backend/targets/${targetId}/history`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error("Failed to clear Q&A history. Please try again.");
      }

      setHistoryState({ targetId, entries: [] });
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorState({ targetId, message: err.message });
      } else {
        setErrorState({ targetId, message: String(err) });
      }
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="p-4 mt-6 border rounded-lg bg-zinc-900 border-zinc-800 shadow-sm text-zinc-100">
      <h3 className="text-lg font-semibold mb-2 text-zinc-100">Ask ReviewLens AI</h3>

      {/* S2-017: show which target the questions are about */}
      {targetName && (
        <p className="text-sm text-zinc-400 mb-3">
          Active target: <span className="font-medium text-zinc-100">{targetName}</span>
        </p>
      )}

      {/* S2-020: explain why questions are unavailable instead of showing a normal Ask box */}
      {blockedReason && (
        <p role="status" className="mb-3 rounded-md border border-amber-700 bg-amber-950/40 p-3 text-sm text-amber-200">
          {blockedReason}
        </p>
      )}

      <form onSubmit={handleAskQuestion} className="flex gap-2 mb-4">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about these reviews..."
          className="flex-1 p-2 border rounded-md bg-zinc-950 border-zinc-700 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={loading || !!blockedReason}
        />
        <button
          type="submit"
          disabled={loading || !!blockedReason || !question.trim()}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:bg-zinc-700 disabled:text-zinc-400 transition-colors"
        >
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {error && <p className="text-red-400 text-sm mb-2">{error}</p>}

      {historyLoading && history.length === 0 && (
        <p className="text-sm text-zinc-400">Loading conversation history...</p>
      )}

      {history.length > 0 && (
        <div className="space-y-3 mt-4">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleClearHistory}
              disabled={clearing || loading}
              className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white disabled:opacity-50 transition-colors"
            >
              {clearing ? "Clearing..." : "Clear Q&A History"}
            </button>
          </div>
          {history.map((entry, idx) => (
            <div key={entry.id ?? idx} className="bg-zinc-950 p-4 rounded-md border border-zinc-800 space-y-2">
              <p className="text-sm font-medium text-blue-400">Q: {entry.question}</p>
              <p className="text-zinc-300 whitespace-pre-wrap">{entry.answer}</p>
              {Array.isArray(entry.supporting_reviews) && entry.supporting_reviews.length > 0 && (
                <div className="pt-2 border-t border-zinc-800">
                  <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Supporting reviews</p>
                  <ul className="mt-2 space-y-2">
                    {entry.supporting_reviews.slice(0, MAX_SUPPORTING_REVIEWS).map((review) => (
                      <li key={review.id} className="rounded-md border border-zinc-800 bg-zinc-900 p-3 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Stars rating={review.rating} />
                          {review.reviewed_at && (
                            <span className="text-xs text-zinc-400">{formatDate(review.reviewed_at)}</span>
                          )}
                        </div>
                        <p className="mt-1 text-zinc-300 whitespace-pre-wrap">{review.review_text}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}