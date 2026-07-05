export function fmtUsd(v: number | null | undefined): string {
  if (v == null) return "N/A";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function fmtRoi(v: number | null | undefined): string {
  if (v == null) return "N/A";
  return `${v.toFixed(1)}x`;
}

export function fmtMonths(v: number | null | undefined): string {
  if (v == null) return "N/A";
  return `${v} mo`;
}

export function fmtNum(v: number | null | undefined): string {
  if (v == null) return "N/A";
  return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function titleize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function confColor(v: number | null | undefined): string {
  if (v == null) return "var(--neutral)";
  if (v >= 65) return "var(--defensible)";
  if (v >= 45) return "var(--brand-ink)";
  return "var(--flagged)";
}

// Render a subset of markdown bold (**x**) as <strong> segments.
export function renderBold(text: string): Array<{ b: boolean; t: string }> {
  const parts: Array<{ b: boolean; t: string }> = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ b: false, t: text.slice(last, m.index) });
    parts.push({ b: true, t: m[1] });
    last = re.lastIndex;
  }
  if (last < text.length) parts.push({ b: false, t: text.slice(last) });
  return parts;
}
