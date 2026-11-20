import { afterEach, expect, test } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { ModelText } from "@/components/ModelText";

afterEach(cleanup);

test("renders the subset as elements", () => {
  const { container } = render(
    <ModelText text={"# Title\n\nUse **B-tree** and `CREATE INDEX`.\n\n- one\n- two\n\n```\nSELECT 1;\n```"} />,
  );
  expect(container.querySelector("h1, h2, h3, h4, h5, h6")).toBeNull();
  expect(container.querySelector("strong")?.textContent).toBe("B-tree");
  expect(container.querySelector("p code")?.textContent).toBe("CREATE INDEX");
  expect(container.querySelectorAll("ul li")).toHaveLength(2);
  expect(container.querySelector("pre code")?.textContent).toBe("SELECT 1;");
});

test("injected HTML and links never become elements or attributes", () => {
  const evil = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    "[click](javascript:alert(1))",
    "**<a href='https://evil.example'>x</a>**",
    "```\n</code></pre><script>alert(2)</script>\n```",
    "https://evil.example/plain",
    "- **[bold link](https://evil.example)** in a list",
  ].join("\n\n");
  const { container } = render(<ModelText text={evil} />);
  expect(container.querySelector("script, img, a, iframe")).toBeNull();
  expect(container.querySelectorAll("[href], [src], [onerror], [style]")).toHaveLength(0);
  expect(container.textContent).toContain("<script>alert(1)</script>");
  expect(container.textContent).toContain("click");
  expect(container.textContent).not.toContain("javascript:");
});
