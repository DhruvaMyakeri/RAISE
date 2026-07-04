import type { Company } from "@/lib/types";
import {
  IconCheck,
  IconSupport,
  IconMarketing,
  IconMaintenance,
  IconDatabase,
} from "./icons";

const DESCRIPTIONS: Record<string, string> = {
  customer_support:
    "Mid-market retailer weighing an AI Tier-1 support assistant to deflect routine tickets.",
  marketing:
    "DTC telehealth brand evaluating an AI dynamic creative platform to lift ad conversion.",
  maintenance:
    "Precision manufacturer assessing predictive maintenance to cut downtime and spend.",
};

function categoryIcon(key: string) {
  if (key === "marketing") return <IconMarketing />;
  if (key === "maintenance") return <IconMaintenance />;
  return <IconSupport />;
}

export function CompanyPicker({
  companies,
  selectedId,
  onSelect,
  onViewSource,
  disabled,
}: {
  companies: Company[];
  selectedId: string | null;
  onSelect: (c: Company) => void;
  onViewSource?: (c: Company) => void;
  disabled?: boolean;
}) {
  return (
    <div className="picker-grid">
      {companies.map((c) => {
        const selected = c.id === selectedId;
        return (
          <div
            key={c.id}
            className={`company-card ${selected ? "selected" : ""}`}
            onClick={() => !disabled && onSelect(c)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (!disabled && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault();
                onSelect(c);
              }
            }}
          >
            <span className="cat">
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                {categoryIcon(c.category_key)}
                {c.category}
              </span>
              {onViewSource ? (
                <span
                  className="view-source"
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewSource(c);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.stopPropagation();
                      e.preventDefault();
                      onViewSource(c);
                    }
                  }}
                >
                  <IconDatabase /> View source data
                </span>
              ) : null}
            </span>
            <div className="cname">{c.name}</div>
            <div className="cdesc">{DESCRIPTIONS[c.category_key] ?? ""}</div>
            <div className="pick">
              <span className="tick">{selected ? <IconCheck /> : null}</span>
              {selected ? "Selected" : "Select this company"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
