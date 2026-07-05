import { confColor } from "@/lib/format";

export function ConfidenceRing({ value }: { value: number | null }) {
  const r = 22;
  const c = 2 * Math.PI * r;
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  const dash = (pct / 100) * c;
  const color = confColor(value);
  return (
    <div className="ring">
      <svg width={54} height={54}>
        <circle cx={27} cy={27} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={5} />
        <circle
          cx={27}
          cy={27}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          style={{ transition: "stroke-dasharray 0.7s cubic-bezier(0.22,1,0.36,1)" }}
        />
      </svg>
      <div className="val" style={{ color }}>
        {value == null ? "N/A" : value}
        <small>/100</small>
      </div>
    </div>
  );
}
