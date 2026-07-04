export interface RangeItem {
  tag: string;
  label: string;
  con: number | null;
  likely: number | null;
  opt: number | null;
}

export function RangeChart({
  items,
  max,
  format,
  ticks,
}: {
  items: RangeItem[];
  max: number;
  format: (v: number | null) => string;
  ticks?: number[];
}) {
  const pct = (v: number) => Math.max(0, Math.min(100, (v / max) * 100));

  return (
    <div className="range">
      {items.map((it, i) => {
        const lo = Math.min(it.con ?? 0, it.opt ?? 0);
        const hi = Math.max(it.con ?? 0, it.opt ?? 0);
        const likely = it.likely ?? lo;
        return (
          <div key={it.tag} className={`range-row ${i === 1 ? "b" : "a"}`}>
            <div className="rtop">
              <div className="rlabel">
                <span className="rtag">{it.tag}</span>
                {it.label}
              </div>
              <div className="rlikely">
                likely <b>{format(it.likely)}</b>
              </div>
            </div>
            <div className="range-track">
              <div
                className="range-band"
                style={{ left: `${pct(lo)}%`, width: `${Math.max(1.5, pct(hi) - pct(lo))}%` }}
              />
              <div className="range-marker" style={{ left: `${pct(likely)}%` }} />
            </div>
            <div className="range-ends">
              <span>{format(it.con)} conservative</span>
              <span>{format(it.opt)} optimistic</span>
            </div>
          </div>
        );
      })}

      {ticks && ticks.length ? (
        <div className="range-scale">
          {ticks.map((t) => (
            <span key={t} className="range-tick" style={{ left: `${pct(t)}%` }}>
              {format(t)}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
