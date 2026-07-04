import type { Memo } from "@/lib/types";
import { IconRecommend } from "./icons";

export function RecommendationBanner({ memo }: { memo: Memo }) {
  const rec = memo.recommendation;
  const winner = rec.winner;
  const winnerBranch =
    winner === "A" ? memo.branches[0] : winner === "B" ? memo.branches[1] : null;
  const winnerName = winnerBranch
    ? winnerBranch.branch_label.replace(/^Scenario [AB]\s*—\s*/, "")
    : null;

  return (
    <div className="rec-hero fade-up">
      <div className="rec-hero-top">
        <div className="rec-verdict">
          <span className="medal">
            <IconRecommend />
          </span>
          Recommendation
        </div>
        {winner ? (
          <span className="rec-pick">
            Scenario {winner}
            {winnerName ? ` · ${winnerName}` : ""}
          </span>
        ) : null}
      </div>
      <div className="body">{rec.reasoning}</div>
      {rec.confidence_caveat ? (
        <div className="caveat">
          <IconRecommend width={15} height={15} />
          <span>{rec.confidence_caveat}</span>
        </div>
      ) : null}
    </div>
  );
}
