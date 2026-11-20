import { describe, expect, test } from "vitest";
import { formatHours, stageLabel } from "@/lib/plan";
import { describeStageChange, isRunId } from "@/lib/usePlanRun";

describe("plan helpers", () => {
  test("known stages get their DESIGN labels, unknown ones are de-snake-cased", () => {
    expect(stageLabel("retrieve_knowledge")).toBe("Search the knowledge base");
    expect(stageLabel("double_check_sources")).toBe("Double check sources");
    expect(stageLabel("__")).toBe("Unnamed stage");
  });

  test("effort is rounded and always approximate", () => {
    expect(formatHours(5.6)).toBe("~6 h");
    expect(formatHours(0.4)).toBe("<1 h");
    expect(formatHours(Number.NaN)).toBe("<1 h");
  });

  test("stage changes are described once per change", () => {
    const before = [
      { name: "analyze_job", state: "running" as const },
      { name: "retrieve_knowledge", state: "waiting" as const },
    ];
    const after = [
      { name: "analyze_job", state: "done" as const },
      { name: "retrieve_knowledge", state: "running" as const },
    ];
    expect(describeStageChange(before, after)).toBe("Done: Read the job posting. Now: Search the knowledge base.");
    expect(describeStageChange(after, after)).toBe("");
  });

  test("run ids must be short and URL-safe", () => {
    expect(isRunId("0b6f4a1e-2c3d-4e5f-8a9b-0c1d2e3f4a5b")).toBe(true);
    expect(isRunId("../secret")).toBe(false);
    expect(isRunId("a".repeat(65))).toBe(false);
    expect(isRunId(null)).toBe(false);
  });
});
