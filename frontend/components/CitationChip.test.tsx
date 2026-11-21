import { afterEach, describe, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { CitationChip, pageName, pageNames } from "@/components/CitationChip";
import { cite, planResult } from "@/components/planFixtures";
import { PlanResult } from "@/components/PlanResult";

afterEach(() => cleanup());

const DOCKER_TITLE = "Docker Docs: Get started and Docker concepts";
const overview = cite({
  chunk_id: "d1",
  title: DOCKER_TITLE,
  section: "Next steps",
  source_url: "https://github.com/docker/docs/blob/main/content/get-started/docker-overview.md",
});
const dockerfile = cite({
  chunk_id: "d2",
  title: DOCKER_TITLE,
  section: "Next steps",
  source_url:
    "https://github.com/docker/docs/blob/main/content/get-started/docker-concepts/building-images/writing-a-dockerfile.md",
});

describe("pageName", () => {
  test("last path segment without extension, dashes and underscores as spaces", () => {
    expect(pageName(overview.source_url)).toBe("docker overview");
    expect(pageName("https://example.com/docs/metric_types.md")).toBe("metric types");
    expect(pageName("https://prometheus.io/docs/introduction/overview/")).toBe("overview");
  });

  test("no path or not a URL gives an empty name", () => {
    expect(pageName("https://example.com/")).toBe("");
    expect(pageName("not a url")).toBe("");
  });
});

describe("pageNames", () => {
  test("only chips whose label repeats get a page name", () => {
    const other = cite();
    const names = pageNames([overview, other, dockerfile]);
    expect(names.get(overview.source_url)).toBe("docker overview");
    expect(names.get(dockerfile.source_url)).toBe("writing a dockerfile");
    expect(names.has(other.source_url)).toBe(false);
  });

  test("unique labels stay unchanged", () => {
    expect(pageNames([overview, cite()]).size).toBe(0);
  });
});

describe("CitationChip with a page name", () => {
  test("the page name stays visible when the label is cut", () => {
    render(<CitationChip citation={overview} page="docker overview" />);
    const link = screen.getByRole("link");
    expect(link.textContent).toContain("… (docker overview)");
    expect(link.getAttribute("title")).toBe(`${DOCKER_TITLE}: Next steps (docker overview)`);
  });

  test("without a page name the label is unchanged", () => {
    render(<CitationChip citation={cite()} />);
    expect(screen.getByRole("link").getAttribute("title")).toBe("Indexes: Multicolumn");
  });
});

test("PlanResult: two pages sharing a label get told apart", () => {
  const base = planResult();
  const roadmap = [{ ...base.roadmap[0], resources: [overview, dockerfile] }, ...base.roadmap.slice(1)];
  render(<PlanResult result={{ ...base, roadmap }} />);
  expect(screen.getByRole("link", { name: /Next steps \(docker overview\)/ })).toBeTruthy();
  expect(screen.getByRole("link", { name: /Next steps \(writing a dockerfile\)/ })).toBeTruthy();
});
