"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

export interface QAHistoryEntry {
  id?: string;
  question: string;
  answer: string;
  created_at?: string;
}

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
  const [history, setHistory] = useState<QAHistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState("");

  // S3-007: Restore persisted Q&A history when opening or switching targets
  useEffect(() => {
    let active = true;
    setHistory([]);
    setError("");
    setHistoryLoading(true);

    (async () => {
      try {
        const token = await getToken();
        const response = await fetch(`http://localhost:8000/api/targets/${targetId}/history`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response?.ok) return;
        const data = await response.json();
        if (active && Array.isArray(data)) {
          setHistory(data);
        }
      } catch {
        // Ignore history fetch errors so user can still ask new questions
      } finally {
        if (active) setHistoryLoading(false);
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
    setError("");

    try {
      const token = await getToken();

      const response = await fetch(`http://localhost:8000/api/targets/${targetId}/ask`, {
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
      setHistory((prev) => [
        ...prev,
        {
          id: data.id,
          question: data.question ?? trimmedQuestion,
          answer: data.answer,
          created_at: data.created_at,
        },
      ]);
      setQuestion("");
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(String(err));
      }
    } finally {
      setLoading(false);
    }
  };

  // S3-008: Clear Q&A history for the active target without deleting target or reviews
  const handleClearHistory = async () => {
    if (clearing || history.length === 0) return;

    setClearing(true);
    setError("");

    try {
      const token = await getToken();
      const response = await fetch(`http://localhost:8000/api/targets/${targetId}/history`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error("Failed to clear Q&A history. Please try again.");
      }

      setHistory([]);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(String(err));
      }
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="p-4 mt-6 border rounded-lg bg-zinc-900 border-zinc-800 shadow-sm text-zinc-100">
      <div className="flex items-center justify-between gap-2 mb-2">
        <h3 className="text-lg font-semibold text-zinc-100">Ask ReviewLens AI</h3>
        {history.length > 0 && (
          <button
            type="button"
            onClick={handleClearHistory}
            disabled={clearing || loading}
            className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white disabled:opacity-50 transition-colors"
          >
            {clearing ? "Clearing..." : "Clear Q&A History"}
          </button>
        )}
      </div>

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
          {history.map((entry, idx) => (
            <div key={entry.id ?? idx} className="bg-zinc-950 p-4 rounded-md border border-zinc-800 space-y-2">
              <p className="text-sm font-medium text-blue-400">Q: {entry.question}</p>
              <p className="text-zinc-300 whitespace-pre-wrap">{entry.answer}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}