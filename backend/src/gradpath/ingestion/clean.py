"""Turn fetched HTML or Markdown into Markdown-like plain text. Input is parsed, never executed."""

import re

from bs4 import BeautifulSoup, NavigableString, Tag

HEADING_ID_RE = re.compile(r"\s*\{#[\w.-]+\}\s*$")
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


# Docs sites write templates into their Markdown source (T-009): Hugo shortcodes (Kubernetes,
# Docker: {{< glossary_tooltip text="Pods" >}}), Liquid tags (GitHub Docs:
# {% data variables.product.prodname_actions %}) and MDX/JSX components on their own line
# (LangChain, RabbitMQ: <Step title="...">). Left in, they are noise in chunks and embeddings.
SHORTCODE_RE = re.compile(r"\{\{[<%]\s*(/?)\s*([\w-]+)([^}]*?)\s*[>%]\}\}")
LIQUID_RE = re.compile(r"\{%-?\s*(\w+)([^%]*?)-?%\}")
JSX_LINE_RE = re.compile(r"^\s*<(/?)([A-Z][\w.]*)((?:\s[^>]*)?)\s*/?>\s*$")
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
CALLOUTS = {"note": "Note:", "caution": "Caution:", "warning": "Warning:", "tip": "Tip:"}
PRODUCT_NAMES = {
    "prodname_actions": "GitHub Actions",
    "prodname_dotcom": "GitHub",
    "github": "GitHub",
    "prodname_ghe_server": "GitHub Enterprise Server",
    "prodname_ghe_cloud": "GitHub Enterprise Cloud",
}


def _attrs(raw: str) -> dict[str, str]:
    return dict(ATTR_RE.findall(raw))


def _shortcode(m: re.Match) -> str:
    """A Hugo shortcode -> the words it stands for, or nothing."""
    closing, name, attrs = m.group(1), m.group(2).lower(), _attrs(m.group(3))
    if closing:
        return ""
    if name == "glossary_tooltip":
        return attrs.get("text") or attrs.get("term_id", "").replace("-", " ")
    if name in CALLOUTS:
        return CALLOUTS[name]
    if name in ("tab", "button"):
        label = attrs.get("name") or attrs.get("text", "")
        return f"{label}:" if name == "tab" and label else label
    return ""  # code_sample, feature-state, param, heading, tabs, ...: no readable text here


def _liquid(m: re.Match) -> str:
    """A Liquid tag -> a product name for `data variables...`, nothing for anything else
    (`data reusables...` points at text we don't have; if/raw/endif only control rendering)."""
    tag, rest = m.group(1), m.group(2).strip()
    if tag == "data" and rest.startswith("variables."):
        key = rest.rsplit(".", 1)[-1]
        return PRODUCT_NAMES.get(key, key.removeprefix("prodname_").replace("_", " "))
    return ""


def _jsx_line(m: re.Match) -> str:
    """A JSX component alone on a line -> its title or label, or nothing."""
    if m.group(1):
        return ""
    attrs = _attrs(m.group(3))
    return attrs.get("title") or attrs.get("label") or ""


def strip_templates(line: str) -> str:
    """Remove Hugo, Liquid and JSX template markup from one line outside code fences; called
    by `clean_markdown`. Keeps the readable text the markup stood for."""
    line = SHORTCODE_RE.sub(_shortcode, line)
    line = LIQUID_RE.sub(_liquid, line)
    return JSX_LINE_RE.sub(_jsx_line, line)


def clean_markdown(md: str) -> tuple[str, str]:
    """Markdown -> (title_guess, text): drop front matter, HTML comments, MDX import/export and
    template markup (`strip_templates`). Code fences are kept as they are."""
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
        elif not in_fence:
            stripped = strip_templates(line)
            if stripped.strip() == "" and line.strip() != "":
                continue  # the line held only markup
            line = stripped
            if line.lstrip().startswith("#"):
                line = HEADING_ID_RE.sub("", line)  # "## Title {#title-id}" -> "## Title"
        lines.append(line)
    text = _collapse("\n".join(lines))
    match = re.search(r"^#\s+(.+)$", text, re.M)
    return (match.group(1).strip() if match else ""), text


def clean_page(content: str, kind: str) -> tuple[str, str]:
    """Dispatch on page kind (`md` or `html`); called by ingest.py."""
    return clean_markdown(content) if kind == "md" else clean_html(content)
