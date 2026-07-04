"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { streamUrl } from "./api";
import type { AgentEvent, Memo, Recommendation, Verdict } from "./types";

export type StageStatus = "pending" | "running" | "complete" | "error";

export interface ScenarioResult {
  roi: number | null;
  payback_months: number | null;
  annual_value_usd: number | null;
  total_cost_3y_usd: number | null;
}

export interface BranchState {
  id: string;
  label: string;
  field: string;
  value: string;
  retrieval: { status: StageStatus; claims: Verdict[] };
  modeling: {
    status: StageStatus;
    scenarios: Record<string, ScenarioResult>;
  };
  explainability: { status: StageStatus; text: string };
}

export interface RunState {
  status: "idle" | "running" | "done" | "error";
  planner: {
    status: StageStatus;
    plan: Memo["plan"] | null;
    branchField: string | null;
  };
  branches: BranchState[];
  activeBranchId: string | null;
  recommendation: { status: StageStatus; data: Recommendation | null };
  memo: Memo | null;
  error: string | null;
}

const initialState: RunState = {
  status: "idle",
  planner: { status: "pending", plan: null, branchField: null },
  branches: [],
  activeBranchId: null,
  recommendation: { status: "pending", data: null },
  memo: null,
  error: null,
};

type Action =
  | { type: "reset" }
  | { type: "begin" }
  | { type: "event"; event: AgentEvent };

function newBranch(id: string, label: string, field: string, value: string): BranchState {
  return {
    id,
    label,
    field,
    value,
    retrieval: { status: "pending", claims: [] },
    modeling: { status: "pending", scenarios: {} },
    explainability: { status: "pending", text: "" },
  };
}

function mapBranch(
  state: RunState,
  branchId: string,
  fn: (b: BranchState) => BranchState
): BranchState[] {
  return state.branches.map((b) => (b.id === branchId ? fn(b) : b));
}

function reducer(state: RunState, action: Action): RunState {
  switch (action.type) {
    case "reset":
      return initialState;
    case "begin":
      return { ...initialState, status: "running", planner: { ...initialState.planner, status: "running" } };
    case "event":
      return applyEvent(state, action.event);
    default:
      return state;
  }
}

function applyEvent(state: RunState, evt: AgentEvent): RunState {
  const { event, data } = evt;
  switch (event) {
    case "planner_started":
      return { ...state, status: "running", planner: { ...state.planner, status: "running" } };

    case "planner_result": {
      const branchPlan = data.branch_plan ?? {};
      const field: string = branchPlan.branch_field ?? "architecture";
      const branchDefs: any[] = branchPlan.branches ?? [];
      const branches = branchDefs.slice(0, 2).map((b) =>
        newBranch(b.branch_id, b.label ?? b.branch_id, field, String(b[field] ?? "?"))
      );
      return {
        ...state,
        planner: { status: "complete", plan: data.plan ?? null, branchField: field },
        branches,
      };
    }

    case "retrieval_started":
      return {
        ...state,
        activeBranchId: data.branch_id,
        branches: mapBranch(state, data.branch_id, (b) => ({
          ...b,
          retrieval: { ...b.retrieval, status: "running" },
        })),
      };

    case "retrieval_claim":
      return {
        ...state,
        branches: mapBranch(state, data.branch_id, (b) => ({
          ...b,
          retrieval: {
            ...b.retrieval,
            claims: [
              ...b.retrieval.claims,
              {
                claim: data.claim,
                verdict: data.verdict,
                reasoning: data.reasoning,
                cited_fact_id: data.cited_fact_id,
              },
            ],
          },
        })),
      };

    case "retrieval_complete":
      return {
        ...state,
        branches: mapBranch(state, data.branch_id, (b) => ({
          ...b,
          retrieval: {
            status: "complete",
            claims: b.retrieval.claims.length
              ? b.retrieval.claims
              : (data.verdicts ?? []),
          },
        })),
      };

    case "modeling_started":
      return {
        ...state,
        activeBranchId: data.branch_id,
        branches: mapBranch(state, data.branch_id, (b) => ({
          ...b,
          modeling: { ...b.modeling, status: "running" },
        })),
      };

    case "modeling_result":
      return {
        ...state,
        branches: mapBranch(state, data.branch_id, (b) => {
          const scenarios = {
            ...b.modeling.scenarios,
            [data.scenario]: {
              roi: data.roi,
              payback_months: data.payback_months,
              annual_value_usd: data.annual_value_usd,
              total_cost_3y_usd: data.total_cost_3y_usd,
            },
          };
          const done = Object.keys(scenarios).length >= 3;
          return {
            ...b,
            modeling: { status: done ? "complete" : "running", scenarios },
          };
        }),
      };

    case "explainability_started":
      return {
        ...state,
        activeBranchId: data.branch_id,
        branches: mapBranch(state, data.branch_id, (b) => ({
          ...b,
          modeling: { ...b.modeling, status: "complete" },
          explainability: { ...b.explainability, status: "running" },
        })),
      };

    case "explainability_chunk":
      return {
        ...state,
        branches: mapBranch(state, data.branch_id, (b) => ({
          ...b,
          explainability: {
            ...b.explainability,
            text: b.explainability.text + (data.chunk ?? ""),
          },
        })),
      };

    case "explainability_complete":
      return {
        ...state,
        branches: mapBranch(state, data.branch_id, (b) => ({
          ...b,
          explainability: { ...b.explainability, status: "complete" },
        })),
      };

    case "recommendation_started":
      return { ...state, recommendation: { status: "running", data: null } };

    case "recommendation_result":
      return {
        ...state,
        recommendation: {
          status: "complete",
          data: data as Recommendation,
        },
      };

    case "memo_ready":
      return { ...state, status: "done", memo: data as Memo };

    case "error":
      return {
        ...state,
        status: "error",
        error: data?.message ?? "Unknown pipeline error",
      };

    default:
      return state;
  }
}

export function useAgentRun() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const esRef = useRef<EventSource | null>(null);
  const finishedRef = useRef(false);

  const closeStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const start = useCallback(
    (categoryKey: string, companyId: string) => {
      closeStream();
      finishedRef.current = false;
      dispatch({ type: "begin" });
      const es = new EventSource(streamUrl(categoryKey, companyId));
      esRef.current = es;

      es.onmessage = (e: MessageEvent) => {
        let parsed: AgentEvent;
        try {
          parsed = JSON.parse(e.data);
        } catch {
          return;
        }
        dispatch({ type: "event", event: parsed });
        if (parsed.event === "memo_ready" || parsed.event === "error") {
          finishedRef.current = true;
          closeStream();
        }
      };

      es.onerror = () => {
        // The browser fires onerror on the normal end-of-stream close too;
        // only surface a real error if the run had not finished yet.
        closeStream();
        if (finishedRef.current) return;
        finishedRef.current = true;
        dispatch({
          type: "event",
          event: {
            event: "error",
            data: { message: "Connection to the analysis stream was lost." },
          },
        });
      };
    },
    [closeStream]
  );

  const reset = useCallback(() => {
    closeStream();
    finishedRef.current = false;
    dispatch({ type: "reset" });
  }, [closeStream]);

  useEffect(() => () => closeStream(), [closeStream]);

  return { state, start, reset };
}
