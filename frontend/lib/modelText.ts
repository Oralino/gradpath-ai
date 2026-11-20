// Parser for the small, safe markdown subset GradPath shows in model text (owner decision
// 2026-11-20): paragraphs, "-"/"*"/"1." lists, "#" headings (shown as bold lines, not <h*>),
// fenced code, `inline code` and **bold**. Everything else stays literal text. It returns plain
// data, never HTML: components/ModelText.tsx turns it into React elements, so React escapes every
// character and nothing here can create a tag, an attribute or a link. Markdown links keep their
// text and drop the URL (model text is never linkified; sources come from the citation list).
// Model and retrieved text is untrusted, so every scan is linear or bounded: no backtracking regex
// over a whole line, no copying arrays per line.

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "strong"; children: Inline[] }
  | { kind: "code"; text: string };

export type Block =
  | { kind: "paragraph"; lines: Inline[][] }
  | { kind: "heading"; inlines: Inline[] }
  | { kind: "list"; ordered: boolean; start: number; items: Inline[][] }
  | { kind: "code"; text: string };

/** Longer input is shown as one plain paragraph without parsing (answers are far shorter). */
export const MAX_PARSE_CHARS = 30_000;
/** A markdown link's text is only looked for this far ahead, so scanning stays bounded. */
const MAX_LINK_TEXT = 200;
const MAX_LINK_URL = 2_000;

// Only fixed-length prefixes are matched with regexes; the rest of the line is sliced, never
// matched, so a long run of spaces can't make a regex backtrack.
const BULLET = /^[ \t]{0,6}[-*+][ \t]/;
const NUMBERED = /^[ \t]{0,6}(\d{1,3})[.)][ \t]/;
const HEADING = /^#{1,6}[ \t]/;
const FENCE = /^[ ]{0,3}(```|~~~)/;

// Index of the ")" that closes a link URL starting at `from`, counting nested parentheses (URLs
// like .../Foo_(bar)). -1 if there is none within MAX_LINK_URL or a space or newline comes first.
function linkUrlEnd(source: string, from: number): number {
  let depth = 0;
  const limit = Math.min(source.length, from + MAX_LINK_URL);
  for (let j = from; j < limit; j++) {
    const c = source[j];
    if (c === " " || c === "\n" || c === "\t") return -1;
    if (c === "(") depth += 1;
    else if (c === ")") {
      if (depth === 0) return j;
      depth -= 1;
    }
  }
  return -1;
}

function backtickRun(source: string, from: number): number {
  let k = 0;
  while (source[from + k] === "`") k += 1;
  return k;
}

// Inline pass, one left-to-right scan. `allowStrong` is false inside **...** so nesting stays one
// level deep. An opener with no valid closer is kept as literal text. Adjacent text is merged.
export function parseInline(source: string, allowStrong = true): Inline[] {
  const out: Inline[] = [];
  let buffer = "";
  const flush = () => {
    if (buffer) out.push({ kind: "text", text: buffer });
    buffer = "";
  };

  let i = 0;
  while (i < source.length) {
    const ch = source[i];

    if (ch === "`") {
      // A code span opens and closes with the same number of backticks (``a`b`` is one span).
      const k = backtickRun(source, i);
      let end = source.indexOf("`".repeat(k), i + k);
      while (end !== -1 && backtickRun(source, end) !== k) {
        end = source.indexOf("`".repeat(k), end + backtickRun(source, end));
      }
      if (end > i + k) {
        flush();
        out.push({ kind: "code", text: source.slice(i + k, end) });
        i = end + k;
      } else {
        buffer += source.slice(i, i + k);
        i += k;
      }
      continue;
    }

    if (allowStrong && ch === "*" && source[i + 1] === "*") {
      const end = source.indexOf("**", i + 2);
      const inner = end > i + 2 ? source.slice(i + 2, end) : "";
      if (inner && inner.trim() === inner) {
        flush();
        out.push({ kind: "strong", children: parseInline(inner, false) });
        i = end + 2;
        continue;
      }
    } else if (ch === "[") {
      // Look only MAX_LINK_TEXT ahead, so a text full of "[" stays bounded.
      const offset = source.slice(i + 1, i + 1 + MAX_LINK_TEXT).indexOf("](");
      const close = offset === -1 ? -1 : i + 1 + offset;
      if (close > i + 1) {
        const urlEnd = linkUrlEnd(source, close + 2);
        if (urlEnd > close + 2) {
          // Keep the link text (with its own bold/code), drop the URL.
          flush();
          out.push(...parseInline(source.slice(i + 1, close), allowStrong));
          i = urlEnd + 1;
          continue;
        }
      }
    }

    buffer += ch;
    i += 1;
  }
  flush();

  const merged: Inline[] = [];
  for (const item of out) {
    const prev = merged[merged.length - 1];
    if (item.kind === "text" && prev?.kind === "text") {
      merged[merged.length - 1] = { kind: "text", text: prev.text + item.text };
    } else {
      merged.push(item);
    }
  }
  return merged;
}

// "# Title ##" -> "Title"; "# Learning C#" keeps its "#" (a closing run needs a space before it).
function headingText(line: string): string {
  let text = line.slice(line.indexOf("#")).replace(/^#+/, "").trim();
  let j = text.length;
  while (j > 0 && text[j - 1] === "#") j -= 1;
  if (j === 0) return "";
  if (j < text.length && (text[j - 1] === " " || text[j - 1] === "\t")) text = text.slice(0, j).trimEnd();
  return text;
}

type ListMatch = { ordered: boolean; start: number; content: string };

function listItem(line: string): ListMatch | null {
  const bullet = BULLET.exec(line);
  if (bullet) return { ordered: false, start: 1, content: line.slice(bullet[0].length).trim() };
  const numbered = NUMBERED.exec(line);
  if (numbered) return { ordered: true, start: Number(numbered[1]), content: line.slice(numbered[0].length).trim() };
  return null;
}

// A ``` line opens a fence only if nothing after the marker contains a backtick (CommonMark), so
// a one-line ```code``` stays inline code.
function fenceMarker(line: string): string | null {
  const match = FENCE.exec(line);
  if (!match) return null;
  if (match[1] === "```" && line.slice(match[0].length).includes("`")) return null;
  return match[1];
}

// Block pass, line by line. Called by components/ModelText.tsx; pure so it can be unit-tested.
export function parseModelText(text: string): Block[] {
  const normalised = text.replace(/\r\n?/g, "\n");
  if (normalised.length > MAX_PARSE_CHARS) {
    return [{ kind: "paragraph", lines: normalised.split("\n").map((l) => [{ kind: "text", text: l }]) }];
  }

  const blocks: Block[] = [];
  let paragraph: Inline[][] | null = null;
  let list: Extract<Block, { kind: "list" }> | null = null;
  const flushParagraph = () => {
    if (paragraph) blocks.push({ kind: "paragraph", lines: paragraph });
    paragraph = null;
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };

  const lines = normalised.split("\n");
  for (let n = 0; n < lines.length; n++) {
    const line = lines[n];

    const fence = fenceMarker(line);
    if (fence) {
      flushParagraph();
      flushList();
      const body: string[] = [];
      n += 1;
      while (n < lines.length && !lines[n].trimStart().startsWith(fence)) {
        body.push(lines[n]);
        n += 1;
      }
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }

    if (line.trim() === "") {
      flushParagraph();
      // A blank line between two items of the same kind keeps one list.
      const current: Extract<Block, { kind: "list" }> | null = list;
      if (current) {
        let next = n + 1;
        while (next < lines.length && lines[next].trim() === "") next += 1;
        const following = next < lines.length ? listItem(lines[next]) : null;
        if (!following || following.ordered !== current.ordered) flushList();
        n = next - 1; // the blank lines are already scanned: skip them (keeps this linear)
      }
      continue;
    }

    if (HEADING.test(line)) {
      flushParagraph();
      flushList();
      const inlines = parseInline(headingText(line));
      if (inlines.length > 0) blocks.push({ kind: "heading", inlines });
      continue;
    }

    const item = listItem(line);
    if (item) {
      flushParagraph();
      const current: Extract<Block, { kind: "list" }> | null = list;
      if (!current || current.ordered !== item.ordered) {
        flushList();
        list = { kind: "list", ordered: item.ordered, start: item.start, items: [] };
      }
      list!.items.push(parseInline(item.content));
      continue;
    }

    // An indented line right after a list item continues that item (in place: no array copies).
    const open: Extract<Block, { kind: "list" }> | null = list;
    if (open && /^[ \t]/.test(line)) {
      open.items[open.items.length - 1].push({ kind: "text", text: " " }, ...parseInline(line.trim()));
      continue;
    }

    flushList();
    paragraph = paragraph ?? [];
    paragraph.push(parseInline(line));
  }
  flushParagraph();
  flushList();
  return blocks;
}
