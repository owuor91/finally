import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import type { Snapshot } from "@/lib/types";
import { usd } from "@/lib/format";

export function PnLChart({ snapshots }: { snapshots: Snapshot[] }) {
  const data = snapshots.map((s) => ({ t: s.recorded_at, value: s.total_value }));

  return (
    <div className="flex h-full flex-col p-2">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Portfolio Value
      </h2>
      <div className="min-h-0 flex-1">
        {data.length < 2 ? (
          <div className="flex h-full items-center justify-center text-xs text-gray-600">
            No history yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 8, bottom: 5, left: 0 }}>
              <YAxis
                domain={["auto", "auto"]}
                width={54}
                tick={{ fill: "#8b949e", fontSize: 10 }}
                tickFormatter={(v) => `$${Math.round(v as number)}`}
              />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #30363d" }}
                labelFormatter={() => ""}
                formatter={(v) => [usd(v as number), "Value"]}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#ecad0a"
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
