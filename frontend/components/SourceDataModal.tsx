"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  CompanyProfile,
  BenchmarkCorpus,
  BenchmarkFact,
} from "@/lib/types";
import { fetchCompanySource, fetchBenchmarks } from "@/lib/api";
import {
  sourceTier,
  TIER_LEGEND,
  citationType,
  isLoadBearing,
  resolveTestNotes,
  formatFactValue,
} from "@/lib/sourceMeta";
import { IconClose, IconDatabase, IconBook, IconFlag } from "./icons";

export interface SourceModalProps {
  companyId: string;
  categoryKey: string;
  companyName: string;
  initialTab?: "profile" | "benchmarks";
  citedFactIds?: string[];
  onClose: () => void;
}

type Tab = "profile" | "benchmarks";

function fmtProfileValue(key: string, value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "number") {
    if (key.includes("usd")) return `$${value.toLocaleString()}`;
    if ((key.includes("rate") || key.includes("share")) && value <= 1) {
      return `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;
    }
    return value.toLocaleString();
  }
  return String(value);
}

function humanize(k: string): string {
  return k
    .replace(/_usd$/, " (USD)")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function SourceDataModal(props: SourceModalProps) {
  const { companyId, categoryKey, companyName, citedFactIds, onClose } = props;
  const [tab, setTab] = useState<Tab>(props.initialTab ?? "profile");
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [corpus, setCorpus] = useState<BenchmarkCorpus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setProfile(null);
    setCorpus(null);
    setError(null);
    Promise.all([fetchCompanySource(companyId), fetchBenchmarks(categoryKey)])
      .then(([p, c]) => {
        if (!alive) return;
        setProfile(p);
        setCorpus(c);
      })
      .catch((e) => alive && setError(String(e.message ?? e)));
    return () => {
      alive = false;
    };
  }, [companyId, categoryKey]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-head">
          <div>
            <div className="modal-eyebrow">Source data · read-only</div>
            <div className="modal-title">{companyName}</div>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <IconClose />
          </button>
        </div>

        <div className="modal-tabs">
          <button
            className={`modal-tab ${tab === "profile" ? "active" : ""}`}
            onClick={() => setTab("profile")}
          >
            <IconDatabase /> Company Profile
            <span className="tab-sub">Synthetic</span>
          </button>
          <button
            className={`modal-tab ${tab === "benchmarks" ? "active" : ""}`}
            onClick={() => setTab("benchmarks")}
          >
            <IconBook /> Benchmark Corpus
            <span className="tab-sub">Real · Cited</span>
          </button>
        </div>

        <div className="modal-body">
          {error ? (
            <div className="src-error">Could not load source data: {error}</div>
          ) : !profile || !corpus ? (
            <div className="src-loading">Loading source data…</div>
          ) : tab === "profile" ? (
            <ProfileTab profile={profile} />
          ) : (
            <BenchmarkTab
              corpus={corpus}
              categoryKey={categoryKey}
              citedFactIds={citedFactIds}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Tab 1 — Company profile
// --------------------------------------------------------------------------
function ProfileTab({ profile }: { profile: CompanyProfile }) {
  const notes = resolveTestNotes(profile);
  const claimField = notes.optimistic_claim_field;
  const unknownField = notes.unknown_trigger_field;

  const overview: [string, unknown][] = [
    ["Industry", profile.industry],
    ["Size", profile.size],
    ["Employees", profile.employees_total],
    ["Annual revenue (USD)", profile.annual_revenue_usd],
    ["Category", profile.project_category],
  ].filter(([, v]) => v != null) as [string, unknown][];

  return (
    <div className="src-tab">
      <div className="src-banner fabricated">
        <IconFlag />
        <div>
          <b>Fabricated demo data, not a real company.</b> Every figure below is
          synthetic, built to exercise the pipeline. Consistent with the memo
          footer: outputs are grounded projections, not financial advice.
        </div>
      </div>

      <div className="src-overview">
        <div className="src-company-name">{profile.company_name}</div>
        {profile.project_description ? (
          <p className="src-desc">{profile.project_description}</p>
        ) : null}
        <div className="src-meta-grid">
          {overview.map(([label, v]) => (
            <div className="src-meta" key={label}>
              <span className="k">{label}</span>
              <span className="v">
                {typeof v === "number" && label.includes("USD")
                  ? `$${v.toLocaleString()}`
                  : String(v)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {claimField ? (
        <div className="src-callout claim">
          <div className="src-callout-head">
            <span className="pill flagged">Intentionally optimistic claim</span>
            <code>{claimField}</code>
          </div>
          <div className="src-callout-body">
            <div className="claim-value">
              {fmtProfileValue(
                claimField,
                (profile.proposed_project ?? {})[claimField] ??
                  notes.optimistic_claim_value
              )}
            </div>
            {notes.why_should_trigger_pushback ? (
              <p>{notes.why_should_trigger_pushback}</p>
            ) : null}
          </div>
        </div>
      ) : null}

      {unknownField && profile.unknown_fields ? (
        <div className="src-callout unknown">
          <div className="src-callout-head">
            <span className="pill unknown">Unresolved, triggers branching</span>
            <code>{unknownField}</code>
          </div>
          <div className="src-callout-body">
            <div className="claim-value muted">
              {String(profile.unknown_fields[unknownField] ?? "unknown")}
            </div>
            <p>
              Because this decision is undecided, the planner splits the analysis
              into two scenario branches and models each independently.
            </p>
          </div>
        </div>
      ) : null}

      <FieldSection
        title="Current operations"
        subtitle="verified company inputs"
        data={profile.current_operations}
      />
      <FieldSection
        title="Proposed project"
        subtitle="proposed build + claims"
        data={profile.proposed_project}
        highlightKey={claimField}
      />

      {profile.notes ? (
        <div className="src-notes">
          <span className="k">Analyst notes</span>
          <p>{profile.notes}</p>
        </div>
      ) : null}
    </div>
  );
}

function FieldSection({
  title,
  subtitle,
  data,
  highlightKey,
}: {
  title: string;
  subtitle: string;
  data?: Record<string, unknown>;
  highlightKey?: string;
}) {
  if (!data || !Object.keys(data).length) return null;
  return (
    <div className="src-section">
      <div className="src-section-head">
        <h4>{title}</h4>
        <span>{subtitle}</span>
      </div>
      <div className="src-fields">
        {Object.entries(data).map(([k, v]) => {
          const hot = k === highlightKey;
          return (
            <div className={`src-field ${hot ? "hot" : ""}`} key={k}>
              <span className="fk">
                {humanize(k)}
                {hot ? <span className="mini-flag">flagged</span> : null}
              </span>
              <span className="fv">{fmtProfileValue(k, v)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Tab 2 — Benchmark corpus
// --------------------------------------------------------------------------
function BenchmarkTab({
  corpus,
  categoryKey,
  citedFactIds,
}: {
  corpus: BenchmarkCorpus;
  categoryKey: string;
  citedFactIds?: string[];
}) {
  const cited = useMemo(() => new Set(citedFactIds ?? []), [citedFactIds]);
  const hasCited = cited.size > 0;
  const [citedOnly, setCitedOnly] = useState(hasCited);
  const citation = citationType(corpus);

  const visible = citedOnly
    ? corpus.facts.filter((f) => cited.has(f.id))
    : corpus.facts;
  const loadBearing = visible.filter((f) => isLoadBearing(categoryKey, f.id));
  const context = visible.filter((f) => !isLoadBearing(categoryKey, f.id));

  return (
    <div className="src-tab">
      <div className="src-banner real">
        <IconBook />
        <div>
          <b>Real, cited benchmark figures.</b>{" "}
          {corpus.honesty_note ??
            "Paraphrased published survey figures used as reference context."}
        </div>
      </div>

      {hasCited ? (
        <div className="src-filter">
          <span>
            {cited.size} fact{cited.size === 1 ? "" : "s"} cited in this run
          </span>
          <button
            className={`filter-toggle ${citedOnly ? "on" : ""}`}
            onClick={() => setCitedOnly((v) => !v)}
          >
            {citedOnly ? "Show full corpus" : "Show only cited facts"}
          </button>
        </div>
      ) : null}

      <div className="tier-legend">
        <span>{TIER_LEGEND[1]}</span>
        <span>{TIER_LEGEND[2]}</span>
        <span>{TIER_LEGEND[3]}</span>
      </div>

      {loadBearing.length ? (
        <div className="fact-group">
          <div className="fact-group-head">
            <h4>Load-bearing facts</h4>
            <span>used as clamps &amp; sanity-check thresholds</span>
          </div>
          {loadBearing.map((f) => (
            <FactCard
              key={f.id}
              fact={f}
              loadBearing
              citation={citation}
              cited={cited.has(f.id)}
            />
          ))}
        </div>
      ) : null}

      {context.length ? (
        <div className="fact-group">
          <div className="fact-group-head">
            <h4>Context facts</h4>
            <span>narrative grounding, not directly clamped</span>
          </div>
          {context.map((f) => (
            <FactCard
              key={f.id}
              fact={f}
              citation={citation}
              cited={cited.has(f.id)}
            />
          ))}
        </div>
      ) : null}

      {!visible.length ? (
        <div className="src-loading">No facts match the current filter.</div>
      ) : null}
    </div>
  );
}

function FactCard({
  fact,
  loadBearing,
  citation,
  cited,
}: {
  fact: BenchmarkFact;
  loadBearing?: boolean;
  citation: "primary" | "secondary";
  cited?: boolean;
}) {
  const tier = sourceTier(fact.source);
  const rows = formatFactValue(fact.value, fact.unit);
  return (
    <div className={`fact-card ${cited ? "cited" : ""}`}>
      <div className="fact-badges">
        <span className={`badge tier t${tier}`}>Tier {tier}</span>
        <span className="badge cite">{citation}</span>
        {loadBearing ? (
          <span className="badge load">load-bearing</span>
        ) : null}
        {cited ? <span className="badge used">cited in run</span> : null}
      </div>
      <div className="fact-claim">{fact.claim}</div>
      <div className="fact-value">
        {rows.map((r, i) => (
          <span className="fv-row" key={i}>
            {r.label ? <em>{r.label}</em> : null}
            <b>{r.text}</b>
          </span>
        ))}
      </div>
      <div className="fact-foot">
        <span className="fsrc">
          {fact.source}
          {fact.source_year ? ` · ${fact.source_year}` : ""}
        </span>
        <code>{fact.id}</code>
      </div>
    </div>
  );
}
