"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchCompanies, fetchIntakeFields, streamUrlForRun } from "@/lib/api";
import type { Company, IntakeFields } from "@/lib/types";
import { useAgentRun } from "@/lib/useAgentRun";
import { CompanyPicker } from "@/components/CompanyPicker";
import { CustomIntake } from "@/components/CustomIntake";
import { AgentTrace } from "@/components/AgentTrace";
import { MemoView } from "@/components/MemoView";
import { SourceDataModal } from "@/components/SourceDataModal";
import { EarlyAccess } from "@/components/EarlyAccess";
import { IconArrow } from "@/components/icons";
import type { Memo } from "@/lib/types";

interface ModalState {
  companyId: string;
  categoryKey: string;
  companyName: string;
  initialTab: "profile" | "benchmarks";
  citedFactIds?: string[];
}

function citedFactIdsFromMemo(memo: Memo): string[] {
  const ids = new Set<string>();
  for (const br of memo.branches) {
    for (const c of br.citations ?? []) {
      if (c.fact_id && c.fact_id !== "none") ids.add(c.fact_id);
    }
    for (const f of br.flagged_assumptions ?? []) {
      if (f.cited_fact_id && f.cited_fact_id !== "none") ids.add(f.cited_fact_id);
    }
  }
  return Array.from(ids);
}

export default function Page() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [mode, setMode] = useState<"demo" | "custom">("demo");
  const [intakeFields, setIntakeFields] = useState<IntakeFields | null>(null);
  const [customRun, setCustomRun] = useState<{ name: string; category: string } | null>(null);
  const { state, start, startUrl, reset } = useAgentRun();

  useEffect(() => {
    fetchCompanies()
      .then((cs) => {
        setCompanies(cs);
        setSelectedId((prev) => prev ?? cs[0]?.id ?? null);
      })
      .catch((e) => setLoadError(String(e.message ?? e)));
    fetchIntakeFields()
      .then(setIntakeFields)
      .catch(() => setIntakeFields(null));
  }, []);

  const selected = useMemo(
    () => companies.find((c) => c.id === selectedId) ?? null,
    [companies, selectedId]
  );

  const running = state.status === "running";
  const showTrace = state.status !== "idle";
  const headerName = customRun?.name ?? selected?.name;
  const headerCategory = customRun?.category ?? selected?.category;

  function handleRun() {
    if (!selected) return;
    setCustomRun(null);
    setTraceOpen(false);
    start(selected.category_key, selected.id);
  }

  function handleCustomRun(runId: string, companyName: string, categoryLabel: string) {
    setCustomRun({ name: companyName, category: categoryLabel });
    setTraceOpen(false);
    startUrl(streamUrlForRun(runId));
  }

  function handleReset() {
    setCustomRun(null);
    reset();
  }

  return (
    <main className="shell">
      {!showTrace ? (
        <>
          <section className="hero">
            <div className="eyebrow" style={{ marginBottom: 18 }}>
              Pre-deployment ROI · document-grounded · benchmark-cited
            </div>
            <h1>
              See the reasoning behind an <span className="accent">AI investment</span>,
              not just the number.
            </h1>
            <p>
              Vantage runs a multi-agent pipeline over a company&apos;s real operating
              data and a corpus of cited industry benchmarks, validating each claim,
              modeling ROI deterministically, and flagging exactly which assumptions
              don&apos;t hold up. Pick a company and watch the agents work in real time.
            </p>
            <div className="hero-meta">
              <span className="chip">
                <b>5</b> agents + <b>1</b> deterministic tool
              </span>
              <span className="chip">
                <b>2</b> scenarios per run
              </span>
              <span className="chip">
                LLMs never compute the <b>final ROI</b>
              </span>
            </div>
          </section>

          <div className="section-head">
            <h2>{mode === "demo" ? "Choose a demo company" : "Analyze your own company"}</h2>
            <div className="mode-tabs" role="tablist" aria-label="Analysis mode">
              <button
                role="tab"
                aria-selected={mode === "demo"}
                className={`mode-tab ${mode === "demo" ? "active" : ""}`}
                onClick={() => setMode("demo")}
              >
                Demo companies
              </button>
              <button
                role="tab"
                aria-selected={mode === "custom"}
                className={`mode-tab ${mode === "custom" ? "active" : ""}`}
                onClick={() => setMode("custom")}
              >
                Your company
              </button>
            </div>
          </div>

          {loadError ? (
            <div
              className="stage error"
              style={{ padding: 18, fontSize: 13.5, color: "var(--flagged)" }}
            >
              Could not reach the API at the configured address. Make sure the backend
              is running (uvicorn on port 8001). Details: {loadError}
            </div>
          ) : mode === "demo" ? (
            <>
              <CompanyPicker
                companies={companies}
                selectedId={selectedId}
                onSelect={(c) => setSelectedId(c.id)}
                onViewSource={(c) =>
                  setModal({
                    companyId: c.id,
                    categoryKey: c.category_key,
                    companyName: c.name,
                    initialTab: "profile",
                  })
                }
              />
              <div className="run-row">
                <button className="btn-run" onClick={handleRun} disabled={!selected}>
                  Run live analysis <IconArrow />
                </button>
                <span className="run-hint">
                  streams planner → retrieval → modeling → explainability → recommendation
                </span>
              </div>
            </>
          ) : intakeFields ? (
            <CustomIntake fields={intakeFields} onRun={handleCustomRun} />
          ) : (
            <div className="stage" style={{ padding: 18, fontSize: 13.5 }}>
              Loading intake form…
            </div>
          )}

          <EarlyAccess />
        </>
      ) : (
        <>
          <div className="section-head" style={{ marginTop: 40 }}>
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>
                {running ? "Live agent trace" : state.status === "error" ? "Run failed" : "Analysis complete"}
              </div>
              <h2 style={{ fontSize: 22 }}>
                {headerName}{" "}
                <span style={{ color: "var(--text-faint)", fontWeight: 500 }}>
                  · {headerCategory}
                </span>
              </h2>
            </div>
            <button className="btn-ghost" onClick={handleReset}>
              {running ? "Cancel" : "New analysis"}
            </button>
          </div>

          {state.status === "error" ? (
            <div
              className="stage error"
              style={{ padding: 18, marginBottom: 16, fontSize: 13.5, color: "var(--flagged)" }}
            >
              {state.error}
            </div>
          ) : null}

          {state.status === "done" && state.memo ? (
            <>
              <MemoView
                memo={state.memo}
                onViewSource={
                  !customRun && selected
                    ? () =>
                        setModal({
                          companyId: selected.id,
                          categoryKey: selected.category_key,
                          companyName: selected.name,
                          initialTab: "benchmarks",
                          citedFactIds: citedFactIdsFromMemo(state.memo!),
                        })
                    : undefined
                }
              />

              <div className="section-head" style={{ marginTop: 40 }}>
                <h2>Full reasoning trace</h2>
                <button
                  className="btn-ghost"
                  style={{ padding: "9px 16px", fontSize: 12.5 }}
                  onClick={() => setTraceOpen((v) => !v)}
                >
                  {traceOpen ? "Hide trace" : "Show trace"}
                </button>
              </div>
              {traceOpen ? <AgentTrace state={state} /> : null}
            </>
          ) : (
            <AgentTrace state={state} />
          )}
        </>
      )}

      <footer
        style={{
          marginTop: 80,
          paddingTop: 20,
          borderTop: "1px solid var(--border)",
          color: "var(--text-faint)",
          fontSize: 12,
          fontFamily: "var(--font-mono)",
        }}
      >
        Vantage · outputs are grounded projections, not financial advice.
      </footer>

      {modal ? (
        <SourceDataModal
          companyId={modal.companyId}
          categoryKey={modal.categoryKey}
          companyName={modal.companyName}
          initialTab={modal.initialTab}
          citedFactIds={modal.citedFactIds}
          onClose={() => setModal(null)}
        />
      ) : null}
    </main>
  );
}
