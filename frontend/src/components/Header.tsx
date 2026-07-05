import type { ConnStatus } from "@/lib/usePrices";
import type { Portfolio } from "@/lib/types";
import { usd, pct, pnlColor } from "@/lib/format";

const DOT: Record<ConnStatus, string> = {
  connected: "bg-up",
  reconnecting: "bg-accent",
  disconnected: "bg-down",
};

const LABEL: Record<ConnStatus, string> = {
  connected: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Disconnected",
};

export function Header({
  portfolio,
  status,
}: {
  portfolio: Portfolio | null;
  status: ConnStatus;
}) {
  const pnl = portfolio?.total_unrealized_pnl ?? 0;
  const pnlPct =
    portfolio && portfolio.positions_value - pnl !== 0
      ? (pnl / (portfolio.positions_value - pnl)) * 100
      : 0;

  return (
    <header className="flex items-center justify-between border-b border-border bg-panel px-4 py-2">
      <div className="flex items-center gap-2">
        <span className="text-lg font-bold text-accent">FinAlly</span>
        <span className="text-xs text-gray-500">AI Trading Workstation</span>
      </div>

      <div className="flex items-center gap-6 text-sm">
        <div>
          <span className="text-gray-500">Cash </span>
          <span className="font-mono text-blue">{usd(portfolio?.cash_balance ?? 0)}</span>
        </div>
        <div>
          <span className="text-gray-500">Total </span>
          <span className="font-mono font-bold">{usd(portfolio?.total_value ?? 0)}</span>
        </div>
        <div className={`font-mono ${pnlColor(pnl)}`}>
          {usd(pnl)} ({pct(pnlPct)})
        </div>
        <div className="flex items-center gap-2" title={LABEL[status]}>
          <span className={`h-2.5 w-2.5 rounded-full ${DOT[status]}`} />
          <span className="text-xs text-gray-400">{LABEL[status]}</span>
        </div>
      </div>
    </header>
  );
}
