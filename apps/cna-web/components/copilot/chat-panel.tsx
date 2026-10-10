"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// ──────────────────────────────────────────────────────────────────────────────
// Grounded copilot chat panel (Phase G). Non-streaming v1: each send POSTs the
// full message list to /api/engagements/[id]/chat and renders the answer with
// citation chips linking to the findings page.
// ──────────────────────────────────────────────────────────────────────────────

type Citation = {
  rule_id: string;
  resource_id: string;
  finding_id: string;
  title: string;
  severity: string;
};

type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};

const SUGGESTIONS = [
  "Which East-West routing gaps are highest risk?",
  "Which public endpoints drive the most cost?",
  "Summarize our perimeter (North-South) exposure.",
  "What single points of failure exist in hybrid connectivity?",
];

const SEV_CHIP: Record<string, string> = {
  CRITICAL: "bg-red-500/15 text-red-600 dark:text-red-400",
  HIGH: "bg-orange-500/15 text-orange-600 dark:text-orange-400",
  MEDIUM: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  LOW: "bg-teal-500/15 text-teal-700 dark:text-teal-300",
};

export function ChatPanel({ engagementId }: { engagementId: string }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  async function send(question?: string) {
    const content = (question ?? input).trim();
    if (!content || loading) return;

    const nextTurns: ChatTurn[] = [...turns, { role: "user", content }];
    setTurns(nextTurns);
    setInput("");
    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`/api/engagements/${engagementId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextTurns.map(({ role, content }) => ({ role, content })),
        }),
      });
      const data = (await res.json()) as {
        answer?: string;
        citations?: Citation[];
        error?: string;
      };
      if (!res.ok || !data.answer) {
        setError(data.error ?? `Copilot request failed (${res.status}).`);
      } else {
        setTurns((prev) => [
          ...prev,
          { role: "assistant", content: data.answer!, citations: data.citations ?? [] },
        ]);
      }
    } catch {
      setError("Copilot is unreachable. Try again shortly.");
    } finally {
      setLoading(false);
      requestAnimationFrame(() =>
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }),
      );
    }
  }

  return (
    <div className="glass rounded-2xl flex flex-col h-[calc(100vh-14rem)] min-h-[28rem]">
      {/* ── Messages ── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4">
        {turns.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-4">
            <p className="text-sm text-navy-600 dark:text-warmgray-300 max-w-md">
              Ask about this engagement&apos;s network assessment — findings, traffic
              direction risks, cost signals, and topology. Answers are grounded in
              discovered data and cite rule IDs.
            </p>
            <div className="flex flex-wrap justify-center gap-2 max-w-xl">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s)}
                  className="glass-sm rounded-full px-3 py-1.5 text-xs text-navy-700 dark:text-warmgray-200 hover:border-teal-400/60 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                turn.role === "user"
                  ? "max-w-[80%] rounded-2xl rounded-br-sm bg-teal-500/15 px-4 py-2.5 text-sm text-navy-800 dark:text-warmgray-100"
                  : "max-w-[85%] rounded-2xl rounded-bl-sm glass-sm px-4 py-3 text-sm"
              }
            >
              {turn.role === "assistant" ? (
                <div className="prose prose-sm dark:prose-invert max-w-none [&_p]:my-1.5 [&_ul]:my-1.5 [&_li]:my-0.5">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
                </div>
              ) : (
                turn.content
              )}

              {turn.citations && turn.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-1.5">
                  {turn.citations.map((c, j) => (
                    <Link
                      key={`${c.rule_id}-${c.resource_id}-${j}`}
                      href={`/engagements/${engagementId}/findings`}
                      title={c.title}
                      className={`rounded-full px-2 py-0.5 text-[11px] font-medium hover:underline ${SEV_CHIP[c.severity] ?? "bg-navy-500/10 text-navy-600 dark:text-warmgray-300"}`}
                    >
                      {c.rule_id}
                      {c.resource_id ? ` · ${c.resource_id.split("/").pop()}` : ""}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="glass-sm rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-navy-500 dark:text-warmgray-300 animate-pulse">
              Consulting assessment data…
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-2.5 text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}
      </div>

      {/* ── Input ── */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        className="border-t border-white/10 p-3 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about findings, traffic risks, costs…"
          aria-label="Ask the assessment copilot a question"
          disabled={loading}
          className="flex-1 rounded-xl glass-sm px-4 py-2.5 text-sm text-navy-800 dark:text-warmgray-100 placeholder:text-navy-400 dark:placeholder:text-warmgray-400 focus:outline-none focus:ring-2 focus:ring-teal-400/50 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="btn-teal rounded-xl px-4 py-2.5 text-sm font-medium disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
