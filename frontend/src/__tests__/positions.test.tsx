import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PositionsTable } from "@/components/PositionsTable";
import type { PriceSnapshot, Position } from "@/lib/types";

const positions: Position[] = [
  {
    ticker: "AAPL",
    quantity: 10,
    avg_cost: 100,
    current_price: 100,
    market_value: 1000,
    unrealized_pnl: 0,
    unrealized_pnl_percent: 0,
  },
];

describe("PositionsTable", () => {
  it("recomputes P&L from the live price feed", () => {
    // Live price 120 vs avg cost 100 over 10 shares => +$200.00, +20.00%
    const prices: PriceSnapshot = {
      AAPL: {
        ticker: "AAPL",
        price: 120,
        previous_price: 119,
        timestamp: 1,
        change: 1,
        change_percent: 0.84,
        direction: "up",
      },
    };
    render(<PositionsTable positions={positions} prices={prices} onSelect={vi.fn()} />);
    expect(screen.getByText("$200.00")).toBeInTheDocument();
    expect(screen.getByText("+20.00%")).toBeInTheDocument();
  });

  it("shows an empty state with no positions", () => {
    render(<PositionsTable positions={[]} prices={{}} onSelect={vi.fn()} />);
    expect(screen.getByText("No positions yet")).toBeInTheDocument();
  });
});
