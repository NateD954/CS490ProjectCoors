"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

export default function ReviewQA({ targetId }: { targetId: string }) {
  const { getToken } = useAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAskQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError("");
    setAnswer("");

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
      setAnswer(data.answer);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 mt-6 border rounded-lg bg-zinc-900 border-zinc-800 shadow-sm text-zinc-100">
      <h3 className="text-lg font-semibold mb-2 text-zinc-100">Ask ReviewLens AI</h3>
      
      <form onSubmit={handleAskQuestion} className="flex gap-2 mb-4">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about these reviews..."
          className="flex-1 p-2 border rounded-md bg-zinc-950 border-zinc-700 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:bg-zinc-700 disabled:text-zinc-400 transition-colors"
        >
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {error && <p className="text-red-400 text-sm mb-2">{error}</p>}
      
      {answer && (
        <div className="bg-zinc-950 p-4 rounded-md border border-zinc-800 mt-4">
          <p className="text-zinc-300 whitespace-pre-wrap">{answer}</p>
        </div>
      )}
    </div>
  );
}