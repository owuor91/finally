import { ResponsiveContainer, Treemap } from "recharts";
import type { Position } from "@/lib/types";
import { pct } from "@/lib/format";

// Green for profit, red for loss; intensity scales with |P&L %|.
function pnlFill(pnlPct: number): string {
  const mag = Math.min(Math.abs(pnlPct) / 10, 1); // saturate at ±10%
  const a = 0.25 + mag * 0.55;
  return pnlPct >= 0 ? `rgba(38,166,154,${a})` : `rgba(239,83,80,${a})`;
}

interface CellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnlPct?: number;
}

function Cell({ x = 0, y = 0, width = 0, height = 0, name, pnlPct = 0 }: CellProps) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{ fill: pnlFill(pnlPct), stroke: "#0d1117", strokeWidth: 2 }}
      />
      {width > 44 && height > 24 && (
        <text x={x + 5} y={y + 16} fill="#fff" fontSize={12} fontWeight={600}>
          {name}
          <tspan x={x + 5} y={y + 30} fontSize={10} fontWeight={400}>
            {pct(pnlPct)}
          </tspan>
        </text>
      )}
    </g>
  );
}

export function PortfolioHeatmap({ positions }: { positions: Position[] }) {
  const data = positions
    .filter((p) => p.market_value > 0)
    .map((p) => ({
      name: p.ticker,
      size: p.market_value,
      pnlPct: p.unrealized_pnl_percent,
    }));

  return (
    <div className="flex h-full flex-col p-2">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Positions Heatmap
      </h2>
      <div className="min-h-0 flex-1">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-gray-600">
            No positions
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap data={data} dataKey="size" content={<Cell />} isAnimationActive={false} />
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
