"use client";

// One preparation plan (DESIGN.md, Screens 3 and Honesty states): the status h2, the banner for
// anything short of complete, an "On this page" nav, then skills gap, roadmap, interview questions
// and, after a fallback, "What still helps". Used by PlanView and the Ask screen. Model and
// retrieved text renders through ModelText or as React text only (DESIGN.md, Security rules).

import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { CitationChip, dedupeByUrl } from "@/components/CitationChip";
import { CitationList } from "@/components/CitationList";
import {
  CheckIcon,
  DashIcon,
  HalfCircleIcon,
  HollowCircleIcon,
  InfoIcon,
  OctagonIcon,
  QuestionIcon,
  TriangleIcon,
} from "@/components/icons";
import { ModelText } from "@/components/ModelText";
import { StatusBadge, type Tone } from "@/components/StatusBadge";
import { PLAN_STATUS, formatHours, stageLabel } from "@/lib/plan";
import type { CareerPrepResult, CritiqueIssue, GapItem, GapStatus, RoadmapItem } from "@/lib/types";

const GAP: Record<GapStatus, { tone: Tone; words: string; group: string; icon: ReactNode }> = {
  not_yet_evidenced: { tone: "gap", words: "Not yet evidenced", group: "Not yet evidenced", icon: <HollowCircleIcon /> },
  partially_evidenced: { tone: "caution", words: "Partly evidenced", group: "Partly evidenced", icon: <HalfCircleIcon /> },
  demonstrated: { tone: "positive", words: "Demonstrated", group: "Demonstrated", icon: <CheckIcon /> },
  not_applicable: {
    tone: "neutral",
    words: "Eligibility (not assessed)",
    group: "Eligibility, not assessed",
    icon: <DashIcon />,
  },
};
// Gaps to address first (DESIGN.md, Screens 3).
const GAP_ORDER: GapStatus[] = ["not_yet_evidenced", "partially_evidenced", "demonstrated", "not_applicable"];

const BANNER: Record<Tone, string> = {
  positive: "border-positive bg-positive-bg",
  caution: "border-caution bg-caution-bg",
  gap: "border-gap bg-gap-bg",
  stopped: "border-stopped bg-stopped-bg",
  info: "border-info bg-info-bg",
  neutral: "border-neutral bg-neutral-bg",
};

// Full class names so Tailwind can see them.
const HEADLINE: Record<Tone, string> = {
  positive: "text-positive",
  caution: "text-caution",
  gap: "text-gap",
  stopped: "text-stopped",
  info: "text-info",
  neutral: "text-neutral",
};

const NOT_PRODUCED = "Not produced in this run";

export interface PlanExtraSection {
  id: string;
  label: string;
  content: ReactNode;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
// "once", "twice", then "3 times": reads naturally in the "Finished with open issues" banner.
const revisedTimes = (n: number) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);

// "After step 2" / "After steps 1 and 3" for depends_on; "" when there is none.
function afterSteps(deps: number[]): string {
  const sorted = [...new Set(deps)].sort((a, b) => a - b);
  if (sorted.length === 0) return "";
  if (sorted.length === 1) return `After step ${sorted[0]}`;
  return `After steps ${sorted.slice(0, -1).join(", ")} and ${sorted[sorted.length - 1]}`;
}

// The result-level banner (DESIGN.md, Status banner). Not dismissible; the h2 sits above it.
function Banner({ tone, icon, headline, children }: { tone: Tone; icon: ReactNode; headline: string; children: ReactNode }) {
  return (
    <div className={`rounded-md border-l-4 p-4 sm:p-6 ${BANNER[tone]}`}>
      <p className={`flex items-center gap-2 text-heading ${HEADLINE[tone]}`}>
        {icon}
        {headline}
      </p>
      <div className="mt-2 space-y-3 text-body">{children}</div>
    </div>
  );
}

function IssueList({ issues }: { issues: CritiqueIssue[] }) {
  return (
    <ul className="space-y-2">
      {issues.map((issue, i) => (
        <li key={`${issue.code}-${i}`} className="flex flex-col items-start gap-2 sm:flex-row text-small">
          {issue.severity === "blocking" ? (
            <StatusBadge tone="stopped" icon={<OctagonIcon />}>
              Blocking
            </StatusBadge>
          ) : (
            <StatusBadge tone="neutral" icon={<InfoIcon />}>
              Minor
            </StatusBadge>
          )}
          <span className="min-w-0 flex-1 whitespace-pre-line">{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}

function Confidence({ level }: { level: GapItem["confidence"] }) {
  if (level === "low") {
    return (
      <span className="inline-flex items-center gap-1 text-meta text-caution">
        <QuestionIcon />
        Low confidence
      </span>
    );
  }
  return <span className="text-meta text-ink-muted">{level === "high" ? "High confidence" : "Medium confidence"}</span>;
}

function NotProduced() {
  return (
    <p className="flex items-center gap-2 rounded-md bg-gap-bg px-3 py-2 text-small text-gap">
      <HollowCircleIcon />
      {NOT_PRODUCED}
    </p>
  );
}

function GapRow({ gap }: { gap: GapItem }) {
  const s = GAP[gap.status] ?? GAP.not_yet_evidenced;
  return (
    <li className="space-y-2 rounded-md border border-rule p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-label">{gap.skill}</h4>
        {gap.importance === "required" ? (
          <span className="inline-flex items-center rounded-sm border border-ink px-2 py-0.5 text-label text-ink">Required</span>
        ) : (
          <StatusBadge tone="neutral" icon={null}>
            Preferred
          </StatusBadge>
        )}
        <StatusBadge tone={s.tone} icon={s.icon}>
          {s.words}
        </StatusBadge>
      </div>
      <ModelText text={gap.reasoning} className="text-small" />
      <Confidence level={gap.confidence} />
    </li>
  );
}

function RoadmapStep({ item, total }: { item: RoadmapItem; total: number }) {
  const after = afterSteps(item.depends_on);
  const chips = dedupeByUrl(item.resources);
  const parts: [string, string][] = [
    ["Why it matters", item.why_it_matters],
    ["Objective", item.objective],
    ["Exercise", item.exercise],
    ["Done when", item.completion_criteria],
  ];
  return (
    <li className="relative space-y-3">
      <span
        aria-hidden="true"
        className="absolute -left-9 top-0 flex h-6 min-w-6 px-1 items-center justify-center rounded-sm border border-rule bg-surface text-meta tabular-nums"
      >
        {item.order}
      </span>
      <p className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-meta text-ink-muted">
        <span>
          Step {item.order} of {total}
          {after && ` · ${after}`}
        </span>
        <span className="tabular-nums">{formatHours(item.effort_hours_estimate)} (estimate)</span>
      </p>
      <h3 className="text-heading">{item.topic}</h3>
      {parts
        .filter(([, text]) => text.trim().length > 0)
        .map(([label, text]) => (
          <div key={label} className="space-y-1">
            <p className="text-label">{label}</p>
            <ModelText text={text} className="text-small" />
          </div>
        ))}
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-small">
          <span className="text-label">Resources:</span>
          {chips.map((c) => (
            <CitationChip key={c.source_url} citation={c} />
          ))}
        </div>
      )}
    </li>
  );
}

export function PlanResult({
  result,
  autoFocus = false,
  headingRef,
  extra,
}: {
  result: CareerPrepResult;
  autoFocus?: boolean;
  headingRef?: RefObject<HTMLHeadingElement | null>;
  extra?: PlanExtraSection;
}) {
  const ownRef = useRef<HTMLHeadingElement>(null);
  const ref = headingRef ?? ownRef;

  // Focus the result h2 when a fresh result arrives (DESIGN.md, Accessibility).
  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus, ref, result]);

  const status = PLAN_STATUS[result.status] ?? PLAN_STATUS.partial;
  const fallback = result.status === "fallback" ? result.fallback : null;
  const stoppedEarly = result.status === "fallback";
  const blocking = result.unresolved_issues.filter((i) => i.severity === "blocking");
  const minor = result.unresolved_issues.filter((i) => i.severity !== "blocking");
  const roadmap = [...result.roadmap].sort((a, b) => a.order - b.order);
  const totalHours = roadmap.reduce((sum, r) => sum + (Number(r.effort_hours_estimate) || 0), 0);

  // "For: {skill}" from the matching gap, else from the job requirement.
  const skillFor = new Map<string, string>();
  for (const r of result.job?.requirements ?? []) skillFor.set(r.id, r.skill);
  for (const g of result.gaps) skillFor.set(g.requirement_id, g.skill);

  const studySources = fallback?.study_sources.filter((s) => s.citations.length > 0) ?? [];
  const helps = fallback !== null && (fallback.answer !== null || studySources.length > 0);

  // After a fallback, sections render only if they have content; otherwise an empty section says
  // so instead of vanishing (DESIGN.md, Honesty states).
  const sections = [
    { id: "plan-gaps", label: "Skills gap", show: !stoppedEarly || result.gaps.length > 0 },
    { id: "plan-roadmap", label: "Roadmap", show: !stoppedEarly || roadmap.length > 0 },
    { id: "plan-questions", label: "Interview questions", show: !stoppedEarly || result.interview_questions.length > 0 },
    { id: "plan-helps", label: "What still helps", show: helps },
    ...(extra ? [{ id: extra.id, label: extra.label, show: true }] : []),
  ].filter((s) => s.show);
  const shown = new Set(sections.map((s) => s.id));

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 ref={ref} tabIndex={-1} className="text-title">
            {status.heading}
          </h2>
          {result.status === "complete" && (
            <StatusBadge tone="positive" icon={<CheckIcon />}>
              {status.badge}
            </StatusBadge>
          )}
        </div>
        {result.status === "complete" && (
          <p className="text-meta text-ink-muted">The final check passed with no blocking issues.</p>
        )}

        {result.status === "complete_with_limitations" && (
          <Banner tone="caution" icon={<TriangleIcon size={20} />} headline={status.badge}>
            <p>
              The plan was revised {revisedTimes(result.revisions_used)} and the final check still found
              problems. Read these before relying on the plan.
            </p>
            {blocking.length > 0 && <IssueList issues={blocking} />}
            <p className="text-small">What you can do: read the issues, then check the steps they affect against the sources.</p>
          </Banner>
        )}
        {result.status === "partial" && (
          <Banner tone="caution" icon={<HalfCircleIcon size={20} />} headline={status.badge}>
            <p>A stage failed or the final check did not run, so parts of this plan are missing or unreviewed.</p>
            {blocking.length > 0 && <IssueList issues={blocking} />}
            <p className="text-small">What you can do: use the parts that are here, or build the plan again.</p>
          </Banner>
        )}
        {result.status === "fallback" && (
          <Banner tone="stopped" icon={<OctagonIcon size={20} />} headline={status.badge}>
            <p className="whitespace-pre-line">{fallback?.message || "The run stopped before it finished."}</p>
            {fallback && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-label">Finished</p>
                  <ul className="space-y-1 text-small">
                    {fallback.completed_stages.length === 0 && <li className="text-ink-muted">None</li>}
                    {fallback.completed_stages.map((name) => (
                      <li key={name} className="flex items-center gap-2">
                        <CheckIcon />
                        {stageLabel(name)}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="space-y-1">
                  <p className="text-label">Not finished</p>
                  <ul className="space-y-1 text-small">
                    {fallback.not_completed.length === 0 && <li className="text-ink-muted">None</li>}
                    {fallback.not_completed.map((name) => (
                      <li key={name} className="flex items-center gap-2">
                        <DashIcon />
                        {stageLabel(name)}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            {blocking.length > 0 && <IssueList issues={blocking} />}
            <p className="text-small">What you can do: start with what still helps below, or try again in a few minutes.</p>
          </Banner>
        )}

        {minor.length > 0 && (
          <details>
            <summary className="cursor-pointer text-label text-link">{plural(minor.length, "minor note", "minor notes")}</summary>
            <div className="mt-2">
              <IssueList issues={minor} />
            </div>
          </details>
        )}
        {result.errors.length > 0 && (
          <details>
            <summary className="cursor-pointer text-label text-link">Technical details</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-meta text-ink-muted">
              {result.errors.map((text, i) => (
                <li key={i} className="whitespace-pre-line">
                  {text}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      <div className="lg:grid lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-12">
        <nav aria-label="Plan sections" className="mb-6 self-start lg:sticky lg:top-20 lg:mb-0">
          <p className="text-label">On this page</p>
          <ul className="mt-1 flex flex-wrap gap-x-4 lg:block">
            {sections.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="inline-block py-1 text-small text-link underline">
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-12">
          {shown.has("plan-gaps") && (
            <section id="plan-gaps" tabIndex={-1} className="space-y-4">
              <h2 className="text-title">Skills gap</h2>
              {result.gaps.length === 0 && <NotProduced />}
              {GAP_ORDER.map((key) => {
                // Required before Preferred inside a group; otherwise the server's order (stable sort).
                const items = result.gaps
                  .filter((g) => g.status === key)
                  .sort((a, b) => Number(a.importance !== "required") - Number(b.importance !== "required"));
                if (items.length === 0) return null;
                return (
                  <div key={key} className="space-y-3">
                    <h3 className="text-heading">
                      {GAP[key].group} ({items.length})
                    </h3>
                    <ul className="space-y-3">
                      {items.map((g, i) => (
                        <GapRow key={`${g.requirement_id}-${i}`} gap={g} />
                      ))}
                    </ul>
                  </div>
                );
              })}
            </section>
          )}

          {shown.has("plan-roadmap") && (
            <section id="plan-roadmap" tabIndex={-1} className="space-y-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h2 className="text-title">Roadmap</h2>
                {roadmap.length > 0 && (
                  <p className="text-meta tabular-nums text-ink-muted">{formatHours(totalHours)} in total (estimate)</p>
                )}
              </div>
              {roadmap.length === 0 ? (
                <NotProduced />
              ) : (
                <ol className="ml-9 space-y-8 border-l border-rule pl-6">
                  {roadmap.map((item) => (
                    <RoadmapStep key={item.order} item={item} total={roadmap.length} />
                  ))}
                </ol>
              )}
            </section>
          )}

          {shown.has("plan-questions") && (
            <section id="plan-questions" tabIndex={-1} className="space-y-4">
              <h2 className="text-title">Interview questions</h2>
              {result.interview_questions.length === 0 ? (
                <NotProduced />
              ) : (
                <ol className="list-decimal space-y-4 pl-6">
                  {result.interview_questions.map((q, i) => {
                    const skill = skillFor.get(q.requirement_id);
                    return (
                      <li key={`${q.requirement_id}-${i}`} className="space-y-1">
                        <h3 className="whitespace-pre-line text-heading">{q.question}</h3>
                        {skill && <p className="text-meta text-ink-muted">For: {skill}</p>}
                        <details>
                          <summary className="cursor-pointer text-label text-link">What a good answer shows</summary>
                          <ModelText text={q.what_a_good_answer_shows} className="mt-2 text-small" />
                        </details>
                      </li>
                    );
                  })}
                </ol>
              )}
            </section>
          )}

          {shown.has("plan-helps") && fallback && (
            <section id="plan-helps" tabIndex={-1} className="space-y-4">
              <h2 className="text-title">What still helps</h2>
              {fallback.answer && (
                <div className="space-y-3 rounded-md border border-rule bg-surface p-4 sm:p-6">
                  <h3 className="text-heading">From the knowledge base</h3>
                  {fallback.answer.status === "insufficient_evidence" ? (
                    <p className="text-small">The knowledge base does not cover this well enough. It did not guess.</p>
                  ) : (
                    <ModelText text={fallback.answer.answer} className="text-body" />
                  )}
                  {fallback.answer.citations.length > 0 && <CitationList citations={fallback.answer.citations} />}
                </div>
              )}
              {studySources.map((s, i) => (
                <div key={`${s.requirement_id}-${i}`} className="space-y-2">
                  <h3 className="text-heading">Study sources: {s.skill}</h3>
                  <CitationList citations={s.citations} />
                </div>
              ))}
            </section>
          )}

          {extra && (
            <section id={extra.id} tabIndex={-1} className="space-y-4">
              {extra.content}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
