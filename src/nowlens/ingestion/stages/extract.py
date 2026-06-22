"""Extract stage.

Parses HTML into a title and a main-content text body using selectolax (fast
lexbor backend). It strips non-content nodes (script/style/nav/header/footer/
aside), prefers semantic main/article containers, converts headings to Markdown
``#`` prefixes, and turns ``<pre>/<code>`` into fenced code blocks so technical
examples survive into chunking.
"""

from __future__ import annotations

from selectolax.parser import HTMLParser, Node

from nowlens.ingestion.models import CrawlResult, ExtractedDocument

_DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "svg",
    "button",
    "iframe",
)
_MAIN_SELECTORS = ("main", "article", "[role=main]", "#content", ".content", ".doc-content")


def _text_of(node: object) -> str:
    return node.text(separator=" ", strip=True)  # type: ignore[attr-defined]


def extract(result: CrawlResult) -> ExtractedDocument:
    tree = HTMLParser(result.html)

    title = ""
    if tree.head is not None:
        title_node = tree.head.css_first("title")
        if title_node is not None:
            title = title_node.text(strip=True)

    for tag in _DROP_TAGS:
        for drop in tree.css(tag):
            drop.decompose()

    # Pick the densest main container, else fall back to <body>.
    container: Node | None = None
    for selector in _MAIN_SELECTORS:
        node = tree.css_first(selector)
        if node is not None and len(_text_of(node)) > 200:
            container = node
            break
    if container is None:
        container = tree.body or tree.root

    lines: list[str] = []
    if container is not None:
        for child in container.traverse(include_text=False):
            tag = child.tag
            if tag in {"h1", "h2", "h3", "h4"}:
                level = int(tag[1])
                text = child.text(strip=True)
                if text:
                    lines.append(f"\n{'#' * level} {text}\n")
            elif tag in {"pre", "code"} and child.parent and child.parent.tag != "pre":
                code = child.text()
                if code and code.strip():
                    lines.append(f"\n```\n{code.strip()}\n```\n")
            elif tag in {"p", "li", "td", "th", "dd", "dt"}:
                text = child.text(separator=" ", strip=True)
                if text:
                    prefix = "- " if tag == "li" else ""
                    lines.append(f"{prefix}{text}")

    text = "\n".join(lines).strip()
    if not text and container is not None:
        text = _text_of(container)

    lang = "en"
    if tree.root is not None:
        html_node = tree.css_first("html")
        if html_node is not None:
            lang = (html_node.attributes.get("lang") or "en").split("-")[0]

    return ExtractedDocument(
        url=result.url,
        title=title or result.url,
        text=text,
        language=lang,
        metadata={"rendered": result.rendered, "content_type": result.content_type},
    )
