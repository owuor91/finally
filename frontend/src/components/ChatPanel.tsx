import { useEffect, useRef, useState } from "react";
import type { ChatMessage, ChatTrade, ChatWatchlistChange } from "@/lib/types";

function TradeChip({ t }: { t: ChatTrade }) {
  const failed = !!t.error;
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs ${
        failed ? "bg-down/20 text-down" : "bg-up/20 text-up"
      }`}
    >
      {t.side.toUpperCase()} {t.quantity} {t.ticker}
      {failed ? ` — ${t.error}` : ""}
    </span>
  );
}

function WatchChip({ w }: { w: ChatWatchlistChange }) {
  return (
    <span className="inline-block rounded bg-blue/20 px-2 py-0.5 text-xs text-blue">
      {w.action === "add" ? "+ " : "− "}
      {w.ticker}
    </span>
  );
}

export function ChatPanel({
  messages,
  loading,
  onSend,
}: {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (text: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (text && !loading) {
      onSend(text);
      setInput("");
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="h-full border-l border-border bg-panel px-2 text-xs text-gray-400 [writing-mode:vertical-rl]"
      >
        AI Chat ▸
      </button>
    );
  }

  return (
    <div className="flex h-full w-80 flex-col border-l border-border bg-panel">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="text-sm font-semibold text-accent">AI Copilot</span>
        <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-gray-300">
          ×
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && (
          <p className="text-xs text-gray-600">
            Ask about your portfolio, or tell me to trade. E.g. &quot;Buy 5 shares of NVDA&quot;.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={`inline-block max-w-[90%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "bg-purple/40 text-white" : "bg-panel-alt text-gray-200"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.content}</div>
              {(m.trades?.length || m.watchlist_changes?.length) && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.trades?.map((t, j) => <TradeChip key={`t${j}`} t={t} />)}
                  {m.watchlist_changes?.map((w, j) => <WatchChip key={`w${j}`} w={w} />)}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="text-left" aria-label="assistant typing">
            <div className="inline-block rounded-lg bg-panel-alt px-3 py-2 text-sm text-gray-400">
              Thinking…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="border-t border-border p-2">
        <div className="flex gap-2">
          <input
            aria-label="Chat message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message FinAlly…"
            className="flex-1 rounded border border-border bg-bg px-2 py-1 text-sm"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded bg-purple px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
