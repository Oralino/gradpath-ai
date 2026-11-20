import { afterEach, describe, expect, test } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { cite, planResult } from "@/components/planFixtures";
import { PlanResult } from "@/components/PlanResult";

afterEach(() => cleanup());

describe("PlanResult", () => {
  test("complete: Checked badge, check line, nav and sections", () => {
    render(<PlanResult result={planResult()} />);
    expect(screen.getByRole("heading", { level: 2, name: "Preparation plan" })).toBeTruthy();
    expect(screen.getByText("Checked")).toBeTruthy();
    expect(screen.getByText("The final check passed with no blocking issues.")).toBeTruthy();
    const nav = screen.getByRole("navigation", { name: "Plan sections" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual([
      "Skills gap",
      "Roadmap",
      "Interview questions",
    ]);
  });

  test("gaps are grouped with gaps to address first, model text through ModelText", () => {
    render(<PlanResult result={planResult()} />);
    const groups = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(groups.indexOf("Not yet evidenced (1)")).toBeLessThan(groups.indexOf("Demonstrated (1)"));
    expect(screen.getByText("SQLite").tagName).toBe("STRONG");
    expect(screen.getByText("Low confidence")).toBeTruthy();
    expect(screen.getByText("High confidence")).toBeTruthy();
  });

  test("roadmap: ordered steps, dependencies, estimates and deduplicated safe chips", () => {
    render(<PlanResult result={planResult()} />);
    expect(screen.getByText("~6 h in total (estimate)")).toBeTruthy();
    expect(screen.getByText("Step 1 of 2")).toBeTruthy();
    expect(screen.getByText("Step 2 of 2 · After step 1")).toBeTruthy();
    expect(screen.getByText("~6 h (estimate)")).toBeTruthy();
    expect(screen.getByText("<1 h (estimate)")).toBeTruthy();
    const topics = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(topics.indexOf("SQL indexing")).toBeLessThan(topics.indexOf("Containers"));
    // two chunks of one page give one chip; the javascript: URL is text, not a link
    expect(screen.getAllByRole("link", { name: /Indexes: Multicolumn/ })).toHaveLength(1);
    expect(screen.queryByRole("link", { name: /Evil/ })).toBeNull();
    expect(screen.getByText("Evil: Multicolumn")).toBeTruthy();
  });

  test("interview questions say which skill they are for", () => {
    render(<PlanResult result={planResult()} />);
    expect(screen.getByRole("heading", { name: "How would you containerise a service?" })).toBeTruthy();
    expect(screen.getByText("For: Docker")).toBeTruthy();
    expect(screen.getByText("What a good answer shows")).toBeTruthy();
  });

  test("complete_with_limitations: caution banner, blocking inline, minor in a disclosure", () => {
    render(
      <PlanResult
        result={planResult({
          status: "complete_with_limitations",
          revisions_used: 2,
          unresolved_issues: [
            { code: "a", message: "Step 2 has no source.", severity: "blocking" },
            { code: "b", message: "Wording.", severity: "minor" },
          ],
        })}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Preparation plan, with open issues" })).toBeTruthy();
    expect(screen.queryByText("Checked")).toBeNull();
    expect(screen.getByText(/revised twice and the final check still found problems/)).toBeTruthy();
    expect(screen.getByText("Step 2 has no source.").closest("details")).toBeNull();
    expect(screen.getByText("Wording.").closest("details")).not.toBeNull();
    expect(screen.getByText("1 minor note")).toBeTruthy();
  });

  test("partial: empty sections say so, errors sit in Technical details", () => {
    render(
      <PlanResult
        result={planResult({ status: "partial", roadmap: [], interview_questions: [], errors: ["plan_roadmap failed"] })}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Partial preparation plan" })).toBeTruthy();
    expect(screen.getByText("Partial plan: not fully checked")).toBeTruthy();
    expect(screen.getAllByText("Not produced in this run")).toHaveLength(2);
    expect(screen.getByText("plan_roadmap failed").closest("details")).not.toBeNull();
  });

  test("fallback: stopped banner with finished lists and What still helps", () => {
    render(
      <PlanResult
        result={planResult({
          status: "fallback",
          gaps: [],
          roadmap: [],
          interview_questions: [],
          fallback: {
            reason: "time_budget",
            failed_stage: null,
            completed_stages: ["analyze_job", "analyze_profile"],
            not_completed: ["plan_roadmap", "new_stage"],
            message: "The workflow ran past its time limit.",
            study_sources: [{ requirement_id: "r-1", skill: "SQL", citations: [cite()] }],
            answer: {
              question: "q",
              status: "answered",
              answer: "Start with **indexes**.",
              citations: [],
              route: "traditional_rag",
              note: null,
            },
          },
        })}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Partial result: the run stopped early" })).toBeTruthy();
    expect(screen.getByText("Stopped early: partial result")).toBeTruthy();
    expect(screen.getByText("The workflow ran past its time limit.")).toBeTruthy();
    expect(screen.getByText("Read the job posting")).toBeTruthy();
    expect(screen.getByText("New stage")).toBeTruthy();
    // sections with no content are left out after a fallback
    expect(screen.queryByRole("heading", { name: "Roadmap" })).toBeNull();
    expect(screen.queryByText("Not produced in this run")).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "What still helps" })).toBeTruthy();
    expect(screen.getByText("Study sources: SQL")).toBeTruthy();
    expect(screen.getByText("indexes").tagName).toBe("STRONG");
  });

  test("autoFocus moves focus to the h2", async () => {
    render(<PlanResult result={planResult()} autoFocus />);
    const heading = screen.getByRole("heading", { level: 2, name: "Preparation plan" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });

  test("the extra section is rendered and linked from the nav", () => {
    render(<PlanResult result={planResult()} extra={{ id: "plan-x", label: "Corrections", content: <p>extra</p> }} />);
    expect(screen.getByRole("link", { name: "Corrections" }).getAttribute("href")).toBe("#plan-x");
    expect(screen.getByText("extra")).toBeTruthy();
  });
  test("inside a gap group, Required comes before Preferred, server order otherwise", () => {
    const gap = planResult().gaps[1];
    const gaps = [
      { ...gap, requirement_id: "a", skill: "Pref A", importance: "preferred" as const },
      { ...gap, requirement_id: "b", skill: "Req B", importance: "required" as const },
      { ...gap, requirement_id: "c", skill: "Pref C", importance: "preferred" as const },
      { ...gap, requirement_id: "d", skill: "Req D", importance: "required" as const },
    ];
    render(<PlanResult result={planResult({ gaps })} />);
    expect(screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual([
      "Req B",
      "Req D",
      "Pref A",
      "Pref C",
    ]);
  });
});
