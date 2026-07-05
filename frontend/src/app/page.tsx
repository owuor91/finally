"use client";

import { useCallback, useEffect, useState } from "react";
import { usePrices } from "@/lib/usePrices";
import * as api from "@/lib/api";
import type { ChatMessage, Portfolio, Side, Snapshot } from "@/lib/types";
import { Header } from "@/components/Header";
import { Watchlist } from "@/components/Watchlist";
import { MainChart } from "@/components/MainChart";
import { PortfolioHeatmap } from "@/components/PortfolioHeatmap";
import { PnLChart } from "@/components/PnLChart";
import { PositionsTable } from "@/components/PositionsTable";
import { TradeBar } from "@/components/TradeBar";
import { ChatPanel } from "@/components/ChatPanel";

const DEFAULT_TICKERS = [
  "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX",
];

export default function Home() {
  const { prices, history, status } = usePrices();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>(DEFAULT_TICKERS);
  const [selected, setSelected] = useState<string | null>("AAPL");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  const refreshPortfolio = useCallback(() => {
    api.getPortfolio().then(setPortfolio).catch(() => {});
  }, []);
  const refreshHistory = useCallback(() => {
    api.getHistory().then(setSnapshots).catch(() => {});
  }, []);
  const refreshWatchlist = useCallback(() => {
    api
      .getWatchlist()
      .then((w) => w.length && setWatchlist(w))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshWatchlist();
    refreshPortfolio();
    refreshHistory();
    const id = setInterval(() => {
      refreshPortfolio();
      refreshHistory();
    }, 15000);
    return () => clearInterval(id);
  }, [refreshWatchlist, refreshPortfolio, refreshHistory]);

  const handleTrade = useCallback(
    async (ticker: string, quantity: number, side: Side) => {
      await api.trade({ ticker, quantity, side });
      refreshPortfolio();
      refreshHistory();
    },
    [refreshPortfolio, refreshHistory],
  );

  const handleAdd = useCallback(
    (t: string) => {
      if (watchlist.includes(t)) return;
      setWatchlist((w) => [...w, t]);
      api.addWatchlist(t).catch(() => refreshWatchlist());
    },
    [watchlist, refreshWatchlist],
  );

  const handleRemove = useCallback((t: string) => {
    setWatchlist((w) => w.filter((x) => x !== t));
    api.removeWatchlist(t).catch(() => {});
  }, []);

  const handleChat = useCallback(
    async (text: string) => {
      setMessages((m) => [...m, { role: "user", content: text }]);
      setChatLoading(true);
      try {
        const res = await api.sendChat(text);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: res.message,
            trades: res.trades,
            watchlist_changes: res.watchlist_changes,
          },
        ]);
        // The AI may have traded or changed the watchlist; resync.
        refreshPortfolio();
        refreshHistory();
        refreshWatchlist();
      } catch (e) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Error: ${e instanceof Error ? e.message : "chat failed"}` },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [refreshPortfolio, refreshHistory, refreshWatchlist],
  );

  return (
    <div className="flex h-screen flex-col bg-bg text-gray-200">
      <Header portfolio={portfolio} status={status} />

      <div className="flex min-h-0 flex-1">
        <aside className="w-72 border-r border-border bg-panel">
          <Watchlist
            tickers={watchlist}
            prices={prices}
            history={history}
            selected={selected}
            onSelect={setSelected}
            onAdd={handleAdd}
            onRemove={handleRemove}
          />
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="grid min-h-0 flex-1 grid-cols-2 grid-rows-2 gap-px bg-border">
            <div className="bg-bg">
              <MainChart ticker={selected} prices={prices} history={history} />
            </div>
            <div className="bg-bg">
              <PnLChart snapshots={snapshots} />
            </div>
            <div className="bg-bg">
              <PortfolioHeatmap positions={portfolio?.positions ?? []} />
            </div>
            <div className="overflow-hidden bg-bg">
              <PositionsTable
                positions={portfolio?.positions ?? []}
                prices={prices}
                onSelect={setSelected}
              />
            </div>
          </div>
          <TradeBar selected={selected} onTrade={handleTrade} />
        </main>

        <ChatPanel messages={messages} loading={chatLoading} onSend={handleChat} />
      </div>
    </div>
  );
}
