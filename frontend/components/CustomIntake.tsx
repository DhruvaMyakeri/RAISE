"use client";

import { useMemo, useRef, useState } from "react";
import { extractProfile, prepareRun } from "@/lib/api";
import type { IntakeField, IntakeFields } from "@/lib/types";
import { IconArrow, IconCheck } from "./icons";

type ExtractState =
  | { kind: "idle" }
  | { kind: "extracting"; filename: string }
  | { kind: "done"; filename: string; found: number; missing: string[] }
  | { kind: "error"; message: string };

const SECTION_LABELS: Record<string, string> = {
  root: "Company",
  current_operations: "Current operations",
  proposed_project: "Proposed AI project",
};

export function CustomIntake({
  fields,
  onRun,
  disabled,
}: {
  fields: IntakeFields;
  onRun: (runId: string, companyName: string, categoryLabel: string) => void;
  disabled?: boolean;
}) {
  const categoryKeys = Object.keys(fields);
  const [category, setCategory] = useState(categoryKeys[0]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [extract, setExtract] = useState<ExtractState>({ kind: "idle" });
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const spec = fields[category];
  const sections = useMemo(() => {
    const bySection = new Map<string, IntakeField[]>();
    for (const f of spec.fields) {
      const list = bySection.get(f.section) ?? [];
      list.push(f);
      bySection.set(f.section, list);
    }
    return Array.from(bySection.entries());
  }, [spec]);

  const missingHighlights =
    extract.kind === "done" ? new Set(extract.missing) : new Set<string>();

  function setValue(name: string, v: string) {
    setValues((prev) => ({ ...prev, [name]: v }));
    setSubmitError(null);
  }

  async function handleFile(file: File) {
    setExtract({ kind: "extracting", filename: file.name });
    setSubmitError(null);
    try {
      const result = await extractProfile(file);
      if (result.category_key && fields[result.category_key]) {
        setCategory(result.category_key);
      }
      setValues((prev) => {
        const next = { ...prev };
        for (const [k, v] of Object.entries(result.values)) next[k] = String(v);
        return next;
      });
      setExtract({
        kind: "done",
        filename: file.name,
        found: Object.keys(result.values).length,
        missing: result.missing_required,
      });
    } catch (err) {
      setExtract({
        kind: "error",
        message: err instanceof Error ? err.message : "Extraction failed.",
      });
    }
  }

  async function handleRun() {
    if (preparing || disabled) return;
    setPreparing(true);
    setSubmitError(null);
    try {
      const runId = await prepareRun(category, values);
      onRun(runId, values.company_name || "Your company", spec.label);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not start the run.");
    } finally {
      setPreparing(false);
    }
  }

  const requiredFilled = spec.fields
    .filter((f) => f.required)
    .every((f) => (values[f.name] ?? "").trim() !== "");

  return (
    <div className="intake">
      <div className="intake-top">
        <div className="intake-cats" role="tablist" aria-label="Project category">
          {categoryKeys.map((key) => (
            <button
              key={key}
              role="tab"
              aria-selected={key === category}
              className={`intake-cat ${key === category ? "active" : ""}`}
              onClick={() => setCategory(key)}
              disabled={disabled}
            >
              {fields[key].label}
            </button>
          ))}
        </div>

        <div className="intake-upload">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = "";
            }}
          />
          <button
            className="btn-ghost"
            onClick={() => fileRef.current?.click()}
            disabled={disabled || extract.kind === "extracting"}
          >
            {extract.kind === "extracting"
              ? `Reading ${extract.filename}…`
              : "Upload a PDF to pre-fill"}
          </button>
          {extract.kind === "done" ? (
            <span className="intake-extract-note ok">
              <IconCheck /> {extract.found} fields extracted from {extract.filename}
              {extract.missing.length > 0
                ? ` — ${extract.missing.length} still needed below`
                : ""}
            </span>
          ) : null}
          {extract.kind === "error" ? (
            <span className="intake-extract-note err">{extract.message}</span>
          ) : null}
        </div>
      </div>

      <p className="intake-branch-note">{spec.branch_question}.</p>

      {sections.map(([section, sectionFields]) => (
        <div key={section} className="intake-section">
          <div className="intake-section-title">{SECTION_LABELS[section] ?? section}</div>
          <div className="intake-grid">
            {sectionFields.map((f) => (
              <label
                key={f.name}
                className={`intake-field ${missingHighlights.has(f.name) ? "missing" : ""}`}
              >
                <span className="intake-label">
                  {f.label}
                  {f.required ? <em> *</em> : null}
                  {f.unit ? <span className="intake-unit">{f.unit}</span> : null}
                </span>
                <input
                  type={f.kind === "text" ? "text" : "number"}
                  step={f.kind === "rate" ? "0.01" : "any"}
                  min={f.kind === "text" ? undefined : 0}
                  max={f.kind === "rate" ? 1 : undefined}
                  placeholder={f.kind === "rate" ? "e.g. 0.35" : ""}
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValue(f.name, e.target.value)}
                  disabled={disabled}
                />
              </label>
            ))}
          </div>
        </div>
      ))}

      <div className="run-row">
        <button
          className="btn-run"
          onClick={handleRun}
          disabled={disabled || preparing || !requiredFilled}
        >
          {preparing ? "Validating…" : <>Run live analysis <IconArrow /></>}
        </button>
        <span className="run-hint">
          {requiredFilled
            ? "your numbers never train anything — they drive one deterministic model run"
            : "fill the required fields (*) to run"}
        </span>
      </div>
      {submitError ? <div className="intake-error">{submitError}</div> : null}
    </div>
  );
}
