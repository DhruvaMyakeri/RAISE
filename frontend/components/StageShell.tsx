import type { ReactNode } from "react";
import type { StageStatus } from "@/lib/useAgentRun";
import { IconCheck } from "./icons";

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: "Queued",
  running: "Running",
  complete: "Done",
  error: "Error",
};

export function StageShell({
  icon,
  title,
  subtitle,
  agent,
  status,
  children,
}: {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  agent?: string;
  status: StageStatus;
  children?: ReactNode;
}) {
  return (
    <div className={`stage ${status}`}>
      <div className="stage-head">
        <div className={`stage-icon ${status === "running" ? "pulse" : ""}`}>{icon}</div>
        <div className="stage-title">
          <div className="t">{title}</div>
          {subtitle ? <div className="s">{subtitle}</div> : null}
        </div>
        {agent ? <div className="stage-agent">{agent}</div> : null}
        <StatusBadge status={status} />
      </div>
      {children ? <div className="stage-body">{children}</div> : null}
    </div>
  );
}

export function StatusBadge({ status }: { status: StageStatus }) {
  return (
    <div className={`stage-status ${status}`}>
      {status === "running" ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className="spinner" /> {STATUS_LABEL[status]}
        </span>
      ) : status === "complete" ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <IconCheck /> {STATUS_LABEL[status]}
        </span>
      ) : (
        STATUS_LABEL[status]
      )}
    </div>
  );
}
