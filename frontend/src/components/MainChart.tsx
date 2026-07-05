import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PriceSnapshot } from "@/lib/types";
import { num, pct, pnlColor } from "@/lib/format";

export function MainChart({
  ticker,
  prices,
  history,
}: {
  ticker: string | null;
  prices: PriceSnapshot;
  history: Record<string, number[]>;
}) {
  const series = ticker ? (history[ticker] ?? []).map((price, i) => ({ i, price })) : [];
  const p = ticker ? prices[ticker] : undefined;

  return (
    <div className="flex h-full flex-col p-3">
      <div className="mb-2 flex items-baseline gap-3">
        <h2 className="text-lg font-bold">{ticker ?? "Select a ticker"}</h2>
        {p && (
          <>
            <span className="font-mono text-xl">{num(p.price)}</span>
            <span className={`font-mono text-sm ${pnlColor(p.change_percent)}`}>
              {pct(p.change_percent)}
            </span>
          </>
        )}
      </div>
      <div className="min-h-0 flex-1">
        {series.length < 2 ? (
          <div className="flex h-full items-center justify-center text-sm text-gray-600">
            Accumulating price history…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <XAxis dataKey="i" hide />
              <YAxis
                domain={["auto", "auto"]}
                width={60}
                tick={{ fill: "#8b949e", fontSize: 11 }}
                tickFormatter={(v) => num(v as number)}
              />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #30363d" }}
                labelFormatter={() => ""}
                formatter={(v) => [num(v as number), ticker ?? ""]}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke="#209dd7"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
