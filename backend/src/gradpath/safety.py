"""Prompt-injection helpers shared by every prompt that wraps untrusted text in tags."""

import functools
import html
import re
import unicodedata

# `<` and the look-alikes NFKC leaves alone (‹ 〈 ⟨ 〈): a model may read any of them as a tag
# opener. NFKC already maps fullwidth ＜ and small ﹤ to `<`.
OPENERS = "<‹〈⟨〈"
# Between the opener and the tag name we skip anything that is not a letter or digit (`/`,
# whitespace, combining marks, fillers), at most this many characters.
MAX_GAP = 12
# Blank "letters" (Hangul fillers) that `\W` does not cover.
FILLERS = "ᅟᅠㅤﾠ"


def normalise_untrusted(text: str) -> str:
    """NFKC (fullwidth and small-form look-alikes -> ASCII), then drop format characters
    (category Cf: zero-width spaces and joiners, bidi controls, soft hyphen, BOM).

    Used by `neutralise_tags`, `escape_attr` and jobs/analyze.py `_normalise`, so quote checks
    compare the same text the model saw (T-008).
    """
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


@functools.cache
def _tag_pattern(tags: tuple[str, ...]) -> re.Pattern[str]:
    names = "|".join(map(re.escape, tags))
    # Match only the opener, when one of our tag names follows within MAX_GAP non-word
    # characters: `</evidence`, `< /evidence`, `<͏/evidence`, `‹/evidence` (T-004, T-008).
    return re.compile(
        rf"[{OPENERS}](?=[\W_{FILLERS}]{{0,{MAX_GAP}}}(?:{names})\b)", re.IGNORECASE | re.UNICODE
    )


def neutralise_tags(text: str, tags: tuple[str, ...]) -> str:
    """Turn the opener of any of our delimiter tags into `&lt;`, so `</evidence` becomes
    `&lt;/evidence`.

    Untrusted text (retrieved chunks, job descriptions, user questions) is wrapped in tags such as
    `<evidence>` or `<job_description>`; if the text contained those tags itself it could close its
    block and pose as instructions. Used by rag/answer.py, jobs/analyze.py and
    workflows/prompting.py. The text is normalised first (`normalise_untrusted`), so invisible
    or fullwidth characters can't hide a tag.
    """
    return _tag_pattern(tags).sub("&lt;", normalise_untrusted(text))


def escape_attr(value: str) -> str:
    """Escape a value placed inside a tag attribute (`source="..."`, `id="..."`).

    Attribute values such as section names come from scraped headings, so a `"` or `>` in them
    could close the attribute and forge markup; `html.escape(quote=True)` turns `& < > " '` into
    entities, after the same normalisation as `neutralise_tags`. Used with `neutralise_tags` by
    rag/answer.py, jobs/analyze.py and workflows/prompting.py.
    """
    return html.escape(normalise_untrusted(value), quote=True)
