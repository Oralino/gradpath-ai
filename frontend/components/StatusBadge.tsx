// Tone badge: icon plus words (DESIGN.md, Status badge). Used by the answer card and the
// temporary plan result. The words carry the meaning; the icon is decoration.

import type { ReactNode } from "react";

export type Tone = "positive" | "caution" | "gap" | "stopped" | "info" | "neutral";

// Full class names so Tailwind can see them.
const BADGE: Record<Tone, string> = {
  positive: "border-positive bg-positive-bg text-positive",
  caution: "border-caution bg-caution-bg text-caution",
  gap: "border-gap bg-gap-bg text-gap",
  stopped: "border-stopped bg-stopped-bg text-stopped",
  info: "border-info bg-info-bg text-info",
  neutral: "border-neutral bg-neutral-bg text-neutral",
};

export function StatusBadge({
  tone,
  icon,
  children,
}: {
  tone: Tone;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-label ${BADGE[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}
