import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Watchlist } from "@/components/Watchlist";
import type { PriceSnapshot } from "@/lib/types";

const prices: PriceSnapshot = {
  AAPL: {
    ticker: "AAPL",
    price: 190.5,
    previous_price: 189,
    timestamp: 1,
    change: 1.5,
    change_percent: 0.79,
    direction: "up",
  },
};

function setup(overrides = {}) {
  const props = {
    tickers: ["AAPL", "MSFT"],
    prices,
    history: { AAPL: [188, 189, 190.5] },
    selected: null,
    onSelect: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  };
  render(<Watchlist {...props} />);
  return props;
}

describe("Watchlist", () => {
  it("renders tickers and live prices", () => {
    setup();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("190.50")).toBeInTheDocument();
  });

  it("calls onAdd with an uppercased ticker", async () => {
    const props = setup();
    await userEvent.type(screen.getByLabelText("Add ticker"), "pypl");
    await userEvent.click(screen.getByRole("button", { name: "+" }));
    expect(props.onAdd).toHaveBeenCalledWith("PYPL");
  });

  it("calls onRemove without selecting the row", async () => {
    const props = setup();
    await userEvent.click(screen.getByLabelText("Remove AAPL"));
    expect(props.onRemove).toHaveBeenCalledWith("AAPL");
    expect(props.onSelect).not.toHaveBeenCalled();
  });

  it("selects a ticker on row click", async () => {
    const props = setup();
    await userEvent.click(screen.getByText("MSFT"));
    expect(props.onSelect).toHaveBeenCalledWith("MSFT");
  });
});
