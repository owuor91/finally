import { useEffect, useRef, useState } from "react";
import { num } from "@/lib/format";

// Renders a price and briefly flashes green/red when it changes.
// Remounting via `key` restarts the CSS animation on every change.
export function PriceCell({ price }: { price: number }) {
  const prev = useRef(price);
  const [flash, setFlash] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (price > prev.current) {
      setFlash("flash-up");
      setTick((t) => t + 1);
    } else if (price < prev.current) {
      setFlash("flash-down");
      setTick((t) => t + 1);
    }
    prev.current = price;
  }, [price]);

  return (
    <span key={tick} className={`rounded px-1 font-mono ${flash}`}>
      {num(price)}
    </span>
  );
}
