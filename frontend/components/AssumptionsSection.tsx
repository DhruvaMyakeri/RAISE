import type { MemoBranch } from "@/lib/types";
import { ConfidencePanel } from "./ConfidencePanel";

export function AssumptionsSection({ branches }: { branches: MemoBranch[] }) {
  const [a, b] = branches;
  if (!a) return null;
  return (
    <div className="conf-grid">
      <ConfidencePanel branch={a} tag="A" />
      {b ? <ConfidencePanel branch={b} tag="B" /> : null}
    </div>
  );
}
