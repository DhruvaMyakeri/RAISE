"use client";

import { useState } from "react";
import type { ExplainDimension, FlaggedAssumption } from "@/lib/types";
import { confColor, renderBold } from "@/lib/format";
import { linkFlagsToDimension } from "@/lib/provenance";
import { FlagItem } from "./FlagItem";
import { IconArrow } from "./icons";

export function DimensionRow({
  dim,
  flags,
}: {
  dim: ExplainDimension;
  flags: FlaggedAssumption[];
}) {
  const [open, setOpen] = useState(false);
  const color = confColor(dim.confidence);
  const width = dim.confidence == null ? 0 : Math.max(0, Math.min(100, dim.confidence));
  const linked = linkFlagsToDimension(dim.text, flags);
  const parts = renderBold(dim.text);

  return (
    <div className={`dim ${open ? "open" : ""}`}>
      <button className="dim-row" onClick={() => setOpen((v) => !v)} type="button">
        <span className="dim-name">{dim.name}</span>
        <span className="dim-bar">
          <span className="dim-fill" style={{ width: `${width}%`, background: color }} />
        </span>
        <span className="dim-score" style={{ color }}>
          {dim.confidence == null ? "—" : dim.confidence}
        </span>
        <span className="dim-chev">
          <IconArrow width={14} height={14} />
        </span>
      </button>
      {open ? (
        <div className="dim-detail">
          <div className="dtext">
            {parts.map((p, i) =>
              p.b ? <strong key={i}>{p.t}</strong> : <span key={i}>{p.t}</span>
            )}
          </div>
          {linked.length ? (
            <div className="linked-flags">
              <div className="lf-title">Assumptions affecting this dimension</div>
              {linked.map((f, i) => (
                <FlagItem key={i} flag={f} />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
