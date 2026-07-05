import { useState } from "react";
import type { Side } from "@/lib/types";

export function TradeBar({
  selected,
  onTrade,
}: {
  selected: string | null;
  onTrade: (ticker: string, quantity: number, side: Side) => Promise<void>;
}) {
  const [ticker, setTicker] = useState("");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const effectiveTicker = (ticker || selected || "").toUpperCase();

  const submit = async (side: Side) => {
    setError("");
    const quantity = parseFloat(qty);
    if (!effectiveTicker || !(quantity > 0)) {
      setError("Enter a ticker and positive quantity");
      return;
    }
    setBusy(true);
    try {
      await onTrade(effectiveTicker, quantity, side);
      setQty("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Trade failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2 border-t border-border bg-panel px-3 py-2">
      <input
        aria-label="Trade ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
        placeholder={selected ?? "Ticker"}
        className="w-24 rounded border border-border bg-bg px-2 py-1 text-sm uppercase"
      />
      <input
        aria-label="Trade quantity"
        type="number"
        min="0"
        step="any"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        placeholder="Qty"
        className="w-24 rounded border border-border bg-bg px-2 py-1 text-sm"
      />
      <button
        onClick={() => submit("buy")}
        disabled={busy}
        className="rounded bg-up px-4 py-1 text-sm font-semibold text-white disabled:opacity-50"
      >
        Buy
      </button>
      <button
        onClick={() => submit("sell")}
        disabled={busy}
        className="rounded bg-down px-4 py-1 text-sm font-semibold text-white disabled:opacity-50"
      >
        Sell
      </button>
      {error && <span className="text-xs text-down">{error}</span>}
    </div>
  );
}
