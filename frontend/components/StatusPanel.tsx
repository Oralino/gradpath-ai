// Result-level panel with a tone, icon and h2 (DESIGN.md, Status banner). Used for the honesty
// states, needs_input, unsupported, busy and error panels. The h2 takes a ref and tabIndex -1 so
// the Ask screen can move focus to it when a result arrives.

import type { ReactNode, Ref } from "react";
import { HollowCircleIcon, InfoIcon, OctagonIcon } from "@/components/icons";
import type { Tone } from "@/components/StatusBadge";

const PANEL: Record<Tone, string> = {
  positive: "border-positive bg-positive-bg",
  caution: "border-caution bg-caution-bg",
  gap: "border-gap bg-gap-bg",
  stopped: "border-stopped bg-stopped-bg",
  info: "border-info bg-info-bg",
  neutral: "border-neutral bg-neutral-bg",
};

function defaultIcon(tone: Tone) {
  if (tone === "stopped") return <OctagonIcon size={20} />;
  if (tone === "gap") return <HollowCircleIcon size={20} />;
  return <InfoIcon size={20} />;
}

export function StatusPanel({
  tone,
  heading,
  headingRef,
  describedBy,
  children,
}: {
  tone: Tone;
  heading: string;
  headingRef?: Ref<HTMLHeadingElement>;
  describedBy?: string; // id of the recording strip, for a recorded result (DESIGN.md)
  children: ReactNode;
}) {
  return (
    <section className={`rounded-md border-l-4 p-4 sm:p-6 ${PANEL[tone]}`}>
      <div className="flex items-center gap-2">
        {defaultIcon(tone)}
        <h2 ref={headingRef} tabIndex={-1} aria-describedby={describedBy} className="text-title">
          {heading}
        </h2>
      </div>
      <div className="mt-2 space-y-3 text-body">{children}</div>
    </section>
  );
}
