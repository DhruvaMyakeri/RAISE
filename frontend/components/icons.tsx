import type { SVGProps } from "react";

const base = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function IconPlanner(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
    </svg>
  );
}

export function IconRetrieval(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export function IconModeling(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 7h8M8 11h8M8 15h4" />
    </svg>
  );
}

export function IconExplain(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <path d="M12 3a6 6 0 0 0-4 10.5c.6.5 1 1.3 1 2.1V17h6v-1.4c0-.8.4-1.6 1-2.1A6 6 0 0 0 12 3Z" />
      <path d="M9 21h6M10 17v4M14 17v4" />
    </svg>
  );
}

export function IconRecommend(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <path d="M12 2 4 5v6c0 5 3.4 8.3 8 10 4.6-1.7 8-5 8-10V5l-8-3Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function IconCheck(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} width={13} height={13} {...p}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function IconFlag(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} width={13} height={13} {...p}>
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V4s-1 1-4 1-5-2-8-2-4 1-4 1Z" />
      <path d="M4 22v-7" />
    </svg>
  );
}

export function IconArrow(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} width={15} height={15} {...p}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export function IconSupport(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
      <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3ZM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3Z" />
    </svg>
  );
}

export function IconMarketing(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <path d="m3 11 18-5v12L3 13v-2Z" />
      <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
    </svg>
  );
}

export function IconMaintenance(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...p}>
      <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.1-2.1 2.7-2.5Z" />
    </svg>
  );
}

export function IconClose(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} width={16} height={16} {...p}>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function IconDatabase(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} width={14} height={14} {...p}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </svg>
  );
}

export function IconBook(p: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} width={14} height={14} {...p}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
    </svg>
  );
}
