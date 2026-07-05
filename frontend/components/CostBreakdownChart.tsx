"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MemoBranch } from "@/lib/types";
import { fmtUsd } from "@/lib/format";

const SEGMENTS = [
  { key: "Build", field: "build_usd", color: "#e8b04b" },
  { key: "Inference", field: "inference_y1_usd", color: "#0ABAB5" },
  { key: "Integration", field: "integration_y1_usd", color: "#7c3ec2" },
  { key: "Model update", field: "model_update_y1_usd", color: "#0c8a52" },
] as const;

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null;
  const total = payload.reduce((s: number, p: any) => s + (p.value ?? 0), 0);
  return (
    <div className="recharts-tt">
      <div className="tt-name">{payload[0]?.payload?.branch}</div>
      {payload.map((p: any) => (
        <div key={p.name} className="tt-row">
          <i style={{ background: p.color }} />
          {p.name}: {fmtUsd(p.value)}
        </div>
      ))}
      <div className="tt-total">Year 1 total: {fmtUsd(total)}</div>
    </div>
  );
}

export function CostBreakdownChart({ branches }: { branches: MemoBranch[] }) {
  const data = branches.map((b, i) => {
    const cb = b.cost_breakdown_likely ?? {};
    const row: Record<string, any> = {
      branch: `Scenario ${i === 0 ? "A" : "B"}`,
    };
    for (const s of SEGMENTS) {
      row[s.key] = (cb as any)[s.field] ?? 0;
    }
    return row;
  });

  return (
    <div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
          barCategoryGap={26}
        >
          <XAxis
            type="number"
            tickFormatter={(v) => fmtUsd(v)}
            tick={{ fill: "#8a8a8a", fontSize: 11, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: "rgba(26,26,26,0.16)" }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="branch"
            tick={{ fill: "#1a1a1a", fontSize: 13, fontWeight: 600 }}
            axisLine={false}
            tickLine={false}
            width={82}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(26,26,26,0.04)" }} />
          {SEGMENTS.map((s) => (
            <Bar key={s.key} dataKey={s.key} stackId="cost" radius={[0, 0, 0, 0]}>
              {data.map((_, idx) => (
                <Cell key={idx} fill={s.color} />
              ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>

      <div className="cost-legend">
        {SEGMENTS.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.key}
          </span>
        ))}
      </div>
    </div>
  );
}
