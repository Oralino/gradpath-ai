"""Turn fetched HTML or Markdown into Markdown-like plain text. Input is parsed, never executed."""

import re

from bs4 import BeautifulSoup, NavigableString, Tag

ANCHOR_GLYPHS = {"¶", "#", "§", "🔗"}
DROP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "svg", "noscript"]
NOISE_RE = re.compile(
    r"(?:^|[-_\s])(?:nav|navbar|navigation|sidebar|breadcrumbs?|toc|menu)(?:$|[-_\s])", re.I
)
INLINE = {
    "a", "span", "code", "strong", "b", "em", "i", "u", "small", "sup", "sub", "abbr", "kbd",
    "mark", "time", "label", "cite", "q", "s", "br", "img",
}  # fmt: skip
FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
MDX_LINE_RE = re.compile(r"^(?:import|export)\s")


def _collapse(text: str) -> str:
    """Trim trailing spaces and squeeze 3+ newlines to one blank line."""
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_noise(tag: Tag) -> bool:
    classes = " ".join(tag.get("class") or [])
    return bool(NOISE_RE.search(classes) or NOISE_RE.search(tag.get("id") or ""))


def _walk(node: Tag, out: list[str]) -> None:
    """Append Markdown blocks for `node`'s children to `out` (recursive; called by clean_html)."""
    buf: list[str] = []

    def flush() -> None:
        text = _squash(" ".join(buf))
        buf.clear()
        if text:
            out.append(text)

    for child in node.children:
        if isinstance(child, NavigableString):
            if type(child).__name__ in {"Comment", "Doctype", "CData"}:
                continue
            buf.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in INLINE:
            buf.append(child.get_text())
        elif name in {"h1", "h2", "h3", "h4"}:
            flush()
            text = _squash(child.get_text())
            if text:
                out.append("#" * int(name[1]) + " " + text)
        elif name in {"h5", "h6"}:
            flush()
            text = _squash(child.get_text())
            if text:
                out.append(f"**{text}**")
        elif name == "pre":
            flush()
            code = child.get_text().strip("\n")
            if code.strip():
                out.append(f"```\n{code}\n```")
        elif name == "li":
            flush()
            nested = [c for c in child.children if isinstance(c, Tag) and c.name in {"ul", "ol"}]
            own = [
                c.get_text() if isinstance(c, Tag) else str(c)
                for c in child.children
                if not any(c is n for n in nested)
            ]
            text = _squash(" ".join(own))
            if text:
                out.append("- " + text)
            for sub in nested:
                _walk(sub, out)
        elif name == "tr":
            flush()
            cells = [_squash(c.get_text(" ")) for c in child.find_all(["td", "th"])]
            if any(cells):
                out.append(" | ".join(cells))
        else:
            flush()
            _walk(child, out)
    flush()


def clean_html(html: str) -> tuple[str, str]:
    """HTML -> (title_guess, Markdown-like text); prefers main/article, drops page chrome."""
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = _squash(soup.title.string)
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    # Heading permalink anchors ("¶" in Python/FastAPI docs, "#" in PostgreSQL docs) would end up
    # in section names and citations.
    for a in soup.find_all("a"):
        if _squash(a.get_text()) in ANCHOR_GLYPHS:
            a.decompose()
    root = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    root = root or soup.body or soup
    for tag in list(root.find_all(True)):
        if not getattr(tag, "decomposed", False) and tag.attrs is not None and _is_noise(tag):
            tag.decompose()
    h1 = root.find("h1")
    if h1 and not title:
        title = _squash(h1.get_text())
    out: list[str] = []
    _walk(root, out)
    return title, _collapse("\n\n".join(out))


def clean_markdown(md: str) -> tuple[str, str]:
    """Markdown -> (title_guess, text): drop front matter, HTML comments, MDX import/export."""
    md = md.replace("\r\n", "\n")
    md = FRONT_MATTER_RE.sub("", md, count=1)
    md = COMMENT_RE.sub("", md)
    lines: list[str] = []
    in_fence = False
    for line in md.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and MDX_LINE_RE.match(line):
            continue
        lines.append(line)
    text = _collapse("\n".join(lines))
    match = re.search(r"^#\s+(.+)$", text, re.M)
    return (match.group(1).strip() if match else ""), text


def clean_page(content: str, kind: str) -> tuple[str, str]:
    """Dispatch on page kind (`md` or `html`); called by ingest.py."""
    return clean_markdown(content) if kind == "md" else clean_html(content)
