// Inline SVG polyline sparkline built from accumulated SSE prices.
// No chart library — a polyline is plenty for a mini-chart.
export function Sparkline({
  data,
  width = 80,
  height = 24,
}: {
  data: number[];
  width?: number;
  height?: number;
}) {
  if (data.length < 2) {
    return <svg width={width} height={height} aria-hidden />;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const step = width / (data.length - 1);
  const points = data
    .map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`)
    .join(" ");
  const rising = data[data.length - 1] >= data[0];

  return (
    <svg width={width} height={height} aria-label="sparkline">
      <polyline
        points={points}
        fill="none"
        stroke={rising ? "#26a69a" : "#ef5350"}
        strokeWidth={1.5}
      />
    </svg>
  );
}
