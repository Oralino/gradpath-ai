import { describe, expect, test } from "vitest";
import { MAX_PARSE_CHARS, parseInline, parseModelText } from "@/lib/modelText";

describe("parseInline", () => {
  test("bold and inline code", () => {
    expect(parseInline("a **b** and `c`")).toEqual([
      { kind: "text", text: "a " },
      { kind: "strong", children: [{ kind: "text", text: "b" }] },
      { kind: "text", text: " and " },
      { kind: "code", text: "c" },
    ]);
  });

  test("code inside bold; bold markers inside code stay literal", () => {
    expect(parseInline("**use `x`**")).toEqual([
      { kind: "strong", children: [{ kind: "text", text: "use " }, { kind: "code", text: "x" }] },
    ]);
    expect(parseInline("`**not bold**`")).toEqual([{ kind: "code", text: "**not bold**" }]);
  });

  test.each(["**unclosed", "** spaced **", "****", "`", "a ` b", "2 * 3 * 4", "snake_case_name"])(
    "leaves %j as literal text",
    (raw) => {
      expect(parseInline(raw)).toEqual([{ kind: "text", text: raw }]);
    },
  );

  test("a markdown link keeps its text and drops the URL", () => {
    expect(parseInline("see [the docs](javascript:alert(1)) now")).toEqual([
      { kind: "text", text: "see the docs now" },
    ]);
  });

  test("HTML stays as text", () => {
    expect(parseInline('<img src=x onerror="alert(1)">')).toEqual([
      { kind: "text", text: '<img src=x onerror="alert(1)">' },
    ]);
  });
});

describe("parseModelText", () => {
  test("paragraphs, bullets, numbered list, heading, fenced code", () => {
    const blocks = parseModelText(
      [
        "## Indexes",
        "Intro line one",
        "line two",
        "",
        "- **B-tree:** best on leading columns",
        "  continued here",
        "* GIN",
        "",
        "3. third",
        "4. fourth",
        "```sql",
        "CREATE INDEX i ON t (a, b);",
        "```",
        "Done.",
      ].join("\r\n"),
    );
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "list", "list", "code", "paragraph"]);
    expect(blocks[1]).toMatchObject({ lines: [[{ text: "Intro line one" }], [{ text: "line two" }]] });
    expect(blocks[2]).toMatchObject({ ordered: false, items: [expect.any(Array), [{ text: "GIN" }]] });
    expect(blocks[2].kind === "list" && blocks[2].items[0].at(-1)).toEqual({ kind: "text", text: "continued here" });
    expect(blocks[3]).toMatchObject({ ordered: true, start: 3 });
    expect(blocks[4]).toEqual({ kind: "code", text: "CREATE INDEX i ON t (a, b);" });
  });

  test("an unclosed fence runs to the end", () => {
    expect(parseModelText("```\nx\ny")).toEqual([{ kind: "code", text: "x\ny" }]);
  });

  test("a bold line is a paragraph, not a bullet", () => {
    expect(parseModelText("**Supported types:** B-tree")[0].kind).toBe("paragraph");
  });

  test("over-long input is not parsed", () => {
    const text = "**a** ".repeat(MAX_PARSE_CHARS / 6 + 1);
    const blocks = parseModelText(text);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ kind: "paragraph", lines: [[{ kind: "text", text }]] });
  });

  test.each([
    ["# Learning C#", "Learning C#"],
    ["## F#", "F#"],
    ["# Title ##", "Title"],
  ])("heading %j keeps its text", (raw, expected) => {
    expect(parseModelText(raw)).toEqual([{ kind: "heading", inlines: [{ kind: "text", text: expected }] }]);
  });

  test("an empty heading renders nothing", () => {
    expect(parseModelText("#   ")).toEqual([]);
  });

  test("a one-line ```code``` is inline code, and the next lines stay paragraphs", () => {
    expect(parseModelText("```print(x)```\nafter")).toEqual([
      { kind: "paragraph", lines: [[{ kind: "code", text: "print(x)" }], [{ kind: "text", text: "after" }]] },
    ]);
  });

  test("link text keeps its bold and code", () => {
    expect(parseInline("[**Doc**](https://x.org) and [`foo`](u)")).toEqual([
      { kind: "strong", children: [{ kind: "text", text: "Doc" }] },
      { kind: "text", text: " and " },
      { kind: "code", text: "foo" },
    ]);
  });

  test("a blank line between items keeps one list", () => {
    const blocks = parseModelText(["- a", "", "- b", "", "after"].join("\n"));
    expect(blocks.map((b) => b.kind)).toEqual(["list", "paragraph"]);
    expect(blocks[0]).toMatchObject({ items: [[{ text: "a" }], [{ text: "b" }]] });
  });

  test("a line with U+2028 is still a list item", () => {
    expect(parseModelText("- a\u2028b")[0].kind).toBe("list");
  });

  test.each([
    ["heading with a long space run", "# a" + " ".repeat(20_000) + "b"],
    ["many continuation lines", "- a\n" + " b\n".repeat(9_000)],
    ["repeated half links", "[a](".repeat(7_000)],
    ["a list followed by many blank lines", "- a" + "\n".repeat(29_000) + "b"],
    ["many blank lines inside one list", "- a" + "\n".repeat(29_000) + "- b"],
    ["bullet with spaces then U+2028", "- " + " ".repeat(20_000) + "\u2028"],
    ["backtick runs of growing length", Array.from({ length: 200 }, (_, k) => "`".repeat(k + 1) + "x").join(" ")],
  ])("stays fast: %s", (_name, input) => {
    const start = performance.now();
    parseModelText(input);
    expect(performance.now() - start).toBeLessThan(500);
  });

  test("adversarial input stays fast", () => {
    const nasty = "[".repeat(10_000) + "`*".repeat(5_000) + "** a".repeat(2_000);
    const start = performance.now();
    parseModelText(nasty);
    expect(performance.now() - start).toBeLessThan(500);
  });
});
