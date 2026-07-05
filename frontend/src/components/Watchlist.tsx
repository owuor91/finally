import { useState } from "react";
import type { PriceSnapshot } from "@/lib/types";
import { pct, pnlColor } from "@/lib/format";
import { PriceCell } from "./PriceCell";
import { Sparkline } from "./Sparkline";

export function Watchlist({
  tickers,
  prices,
  history,
  selected,
  onSelect,
  onAdd,
  onRemove,
}: {
  tickers: string[];
  prices: PriceSnapshot;
  history: Record<string, number[]>;
  selected: string | null;
  onSelect: (t: string) => void;
  onAdd: (t: string) => void;
  onRemove: (t: string) => void;
}) {
  const [input, setInput] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim().toUpperCase();
    if (t) onAdd(t);
    setInput("");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-2 py-1">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Watchlist</h2>
        <form onSubmit={submit} className="flex gap-1">
          <input
            aria-label="Add ticker"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Add"
            className="w-16 rounded border border-border bg-bg px-1 text-xs uppercase"
          />
          <button type="submit" className="rounded bg-blue px-2 text-xs text-white">
            +
          </button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <tbody>
            {tickers.map((t) => {
              const p = prices[t];
              const chgPct = p?.change_percent ?? 0;
              return (
                <tr
                  key={t}
                  onClick={() => onSelect(t)}
                  className={`cursor-pointer border-b border-border/50 hover:bg-panel-alt ${
                    selected === t ? "bg-panel-alt" : ""
                  }`}
                >
                  <td className="px-2 py-1 font-mono font-semibold">{t}</td>
                  <td className="px-1 py-1 text-right">
                    {p ? <PriceCell price={p.price} /> : <span className="text-gray-600">—</span>}
                  </td>
                  <td className={`px-1 py-1 text-right font-mono text-xs ${pnlColor(chgPct)}`}>
                    {p ? pct(chgPct) : ""}
                  </td>
                  <td className="px-1 py-1">
                    <Sparkline data={history[t] ?? []} />
                  </td>
                  <td className="px-1 py-1 text-right">
                    <button
                      aria-label={`Remove ${t}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemove(t);
                      }}
                      className="text-gray-600 hover:text-down"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
