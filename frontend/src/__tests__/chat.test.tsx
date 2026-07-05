import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel } from "@/components/ChatPanel";
import type { ChatMessage } from "@/lib/types";

describe("ChatPanel", () => {
  it("renders messages and inline trade/watchlist confirmations", () => {
    const messages: ChatMessage[] = [
      { role: "user", content: "Buy 5 NVDA" },
      {
        role: "assistant",
        content: "Done — bought 5 NVDA.",
        trades: [{ ticker: "NVDA", side: "buy", quantity: 5 }],
        watchlist_changes: [{ ticker: "PYPL", action: "add" }],
      },
    ];
    render(<ChatPanel messages={messages} loading={false} onSend={vi.fn()} />);
    expect(screen.getByText("Buy 5 NVDA")).toBeInTheDocument();
    expect(screen.getByText("Done — bought 5 NVDA.")).toBeInTheDocument();
    expect(screen.getByText("BUY 5 NVDA")).toBeInTheDocument();
    expect(screen.getByText(/PYPL/)).toBeInTheDocument();
  });

  it("shows a loading indicator while awaiting a response", () => {
    render(<ChatPanel messages={[]} loading onSend={vi.fn()} />);
    expect(screen.getByLabelText("assistant typing")).toBeInTheDocument();
  });

  it("sends a message and clears the input", async () => {
    const onSend = vi.fn();
    render(<ChatPanel messages={[]} loading={false} onSend={onSend} />);
    const input = screen.getByLabelText("Chat message");
    await userEvent.type(input, "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(input).toHaveValue("");
  });

  it("does not send while loading", async () => {
    const onSend = vi.fn();
    render(<ChatPanel messages={[]} loading onSend={onSend} />);
    await userEvent.type(screen.getByLabelText("Chat message"), "hi{enter}");
    expect(onSend).not.toHaveBeenCalled();
  });
});
