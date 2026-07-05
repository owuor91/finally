import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriceCell } from "@/components/PriceCell";

describe("PriceCell flash", () => {
  it("flashes green on an uptick and red on a downtick", () => {
    const { rerender } = render(<PriceCell price={100} />);
    expect(screen.getByText("100.00").className).not.toContain("flash");

    rerender(<PriceCell price={101} />);
    expect(screen.getByText("101.00").className).toContain("flash-up");

    rerender(<PriceCell price={99} />);
    expect(screen.getByText("99.00").className).toContain("flash-down");
  });
});
