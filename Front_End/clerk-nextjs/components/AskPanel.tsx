"use client";
import { useState, type FormEvent } from "react";
import type { ChatMessage } from "@/lib/types";
import { askAboutPlace } from "@/lib/reviews-service";
import { Card } from "./ui/Card";
import { Button } from "./ui/Button";
import { useToast } from "./ui/Toast";

export function AskPanel({ placeId, placeName }: { placeId: string; placeName: string }) {
  const toast = useToast();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) {
      toast.error("Type a question about these reviews first.");
      return;
    }
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: q }]);
    setQuestion("");
    setAsking(true);
    const loadingId = toast.loading("Working on your answer. Please wait.");
    try {
      const answer = await askAboutPlace(placeId, q);
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", content: answer }]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not get an answer. Try again.");
    } finally {
      toast.dismiss(loadingId);
      setAsking(false);
    }
  }

  return (
    <Card className="space-y-4">
      {messages.length === 0 ? (
        <p className="text-zinc-400">
          Ask anything about {placeName} in plain English, like &quot;What do people say about the service?&quot;
        </p>
      ) : (
        <ul className="space-y-3" aria-live="polite">
          {messages.map((m) => (
            <li
              key={m.id}
              className={`max-w-[85%] rounded-lg px-4 py-2 ${
                m.role === "user" ? "ml-auto bg-violet-600 text-white" : "bg-zinc-800 text-zinc-100"
              }`}
            >
              {m.content}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="ask-input" className="sr-only">
          Your question
        </label>
        <input
          id="ask-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about these reviews"
          className="h-11 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-4 text-base text-zinc-100 placeholder:text-zinc-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-400"
        />
        <Button type="submit" loading={asking}>
          Ask question
        </Button>
      </form>
    </Card>
  );
}
