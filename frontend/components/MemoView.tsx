import type { Memo, MemoBranch } from "@/lib/types";
import { fmtRoi, fmtMonths, titleize } from "@/lib/format";
import { RangeChart, type RangeItem } from "./RangeChart";
import { CostBreakdownChart } from "./CostBreakdownChart";
import { RecommendationBanner } from "./RecommendationBanner";
import { AssumptionsSection } from "./AssumptionsSection";
import { IconDatabase } from "./icons";

function shortName(b: MemoBranch): string {
  const s = b.branch_label.replace(/^Scenario [AB]\s*—\s*/, "").trim();
  return s || titleize(b.branch_value);
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const padded = v * 1.15;
  const mag = Math.pow(10, Math.floor(Math.log10(padded)));
  return Math.ceil(padded / (mag / 2)) * (mag / 2);
}

export function MemoView({
  memo,
  onViewSource,
}: {
  memo: Memo;
  onViewSource?: () => void;
}) {
  const [a, b] = memo.branches;

  const roiItems: RangeItem[] = memo.branches.map((br, i) => ({
    tag: i === 0 ? "A" : "B",
    label: shortName(br),
    con: br.metrics.roi_3yr.conservative,
    likely: br.metrics.roi_3yr.likely,
    opt: br.metrics.roi_3yr.optimistic,
  }));
  const roiMax = niceMax(
    Math.max(...memo.branches.map((br) => br.metrics.roi_3yr.optimistic ?? 0))
  );

  const paybackItems: RangeItem[] = memo.branches.map((br, i) => ({
    tag: i === 0 ? "A" : "B",
    label: shortName(br),
    con: br.metrics.payback_months.conservative,
    likely: br.metrics.payback_months.likely,
    opt: br.metrics.payback_months.optimistic,
  }));
  const paybackMax = niceMax(
    Math.max(
      ...memo.branches.flatMap((br) => [
        br.metrics.payback_months.conservative ?? 0,
        br.metrics.payback_months.optimistic ?? 0,
      ])
    )
  );

  return (
    <div className="memo">
      <RecommendationBanner memo={memo} />

      {onViewSource ? (
        <div className="transparency-bar">
          <span>
            Every flagged assumption traces to a company data field and a cited
            benchmark. Inspect the raw inputs behind this analysis.
          </span>
          <button className="view-source strong" onClick={onViewSource}>
            <IconDatabase /> View source data
          </button>
        </div>
      ) : null}

      <div className="section-head" style={{ margin: "10px 0 2px" }}>
        <h2>Scenario comparison</h2>
        <span className="step">
          {shortName(a)} vs {shortName(b)}
        </span>
      </div>

      <div className="chart-grid">
        <div className="chart-card">
          <div className="head">
            <h3>3-year ROI</h3>
            <span className="hint">range: conservative → optimistic</span>
          </div>
          <RangeChart
            items={roiItems}
            max={roiMax}
            format={fmtRoi}
            ticks={[roiMax * 0.25, roiMax * 0.5, roiMax * 0.75]}
          />
        </div>

        <div className="chart-card">
          <div className="head">
            <h3>Payback period</h3>
            <span className="hint">shorter is better</span>
          </div>
          <RangeChart
            items={paybackItems}
            max={paybackMax}
            format={fmtMonths}
            ticks={[paybackMax * 0.25, paybackMax * 0.5, paybackMax * 0.75]}
          />
        </div>
      </div>

      <div className="chart-card">
        <div className="head">
          <h3>Year 1 cost structure</h3>
          <span className="hint">build + inference + integration + model-update</span>
        </div>
        <CostBreakdownChart branches={memo.branches} />
      </div>

      <div className="section-head" style={{ margin: "18px 0 2px" }}>
        <h2>Confidence &amp; assumptions</h2>
        <span className="step">per Slalom dimension · expand for drivers</span>
      </div>
      <AssumptionsSection branches={memo.branches} />
    </div>
  );
}
