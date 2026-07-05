import type { PriceSnapshot, Position } from "@/lib/types";
import { num, pct, pnlColor, usd } from "@/lib/format";

// Live current_price/P&L are recomputed from the SSE feed so the table updates
// between portfolio refreshes; falls back to the server's values.
export function PositionsTable({
  positions,
  prices,
  onSelect,
}: {
  positions: Position[];
  prices: PriceSnapshot;
  onSelect: (t: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <h2 className="px-2 py-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Positions
      </h2>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-panel text-xs text-gray-500">
            <tr>
              <th className="px-2 py-1 text-left">Ticker</th>
              <th className="px-2 py-1 text-right">Qty</th>
              <th className="px-2 py-1 text-right">Avg Cost</th>
              <th className="px-2 py-1 text-right">Price</th>
              <th className="px-2 py-1 text-right">P&L</th>
              <th className="px-2 py-1 text-right">%</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr>
                <td colSpan={6} className="px-2 py-4 text-center text-xs text-gray-600">
                  No positions yet
                </td>
              </tr>
            )}
            {positions.map((p) => {
              const live = prices[p.ticker]?.price ?? p.current_price;
              const pnl = (live - p.avg_cost) * p.quantity;
              const pnlPct = p.avg_cost ? ((live - p.avg_cost) / p.avg_cost) * 100 : 0;
              return (
                <tr
                  key={p.ticker}
                  onClick={() => onSelect(p.ticker)}
                  className="cursor-pointer border-b border-border/50 hover:bg-panel-alt"
                >
                  <td className="px-2 py-1 font-mono font-semibold">{p.ticker}</td>
                  <td className="px-2 py-1 text-right font-mono">{num(p.quantity)}</td>
                  <td className="px-2 py-1 text-right font-mono">{num(p.avg_cost)}</td>
                  <td className="px-2 py-1 text-right font-mono">{num(live)}</td>
                  <td className={`px-2 py-1 text-right font-mono ${pnlColor(pnl)}`}>{usd(pnl)}</td>
                  <td className={`px-2 py-1 text-right font-mono ${pnlColor(pnlPct)}`}>
                    {pct(pnlPct)}
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
