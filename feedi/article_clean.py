"""
Generic cleanup of scraped article html, around the readability pass.

Readability decides what the article is by scoring the page, and it already ignores
elements whose class or id looks like site chrome. That works when a site marks up its
page semantically. Plenty of hand-rolled blogs don't: they drop the nav, the article and
the footer into one container, and the nav rides along into the reader -- which is how
"Archives Categories Blogroll" ended up above the text of a gilesthomas.com post.

So the page is cleaned on both sides of readability:

  strip_chrome()          before, removing elements that announce themselves as chrome by
                          tag, aria role or class name -- but only when they hold no prose
  strip_trailing_appeals() after, removing the subscribe pitches and tip jars that sites
                          append below every article

Both are deliberately timid. Leaving a stray nav link in an article is a cosmetic
annoyance; deleting a paragraph of the article is a bug the reader can't recover from.
Measured across 242 articles from 148 domains, these clear boilerplate on 17 domains
without costing any article measurable text -- see tests/test_article_clean.py for the
cases that pin the risky edges.
"""

import re

from bs4 import BeautifulSoup

PROSE_MIN = 200  # chars of continuous text that mark a block as real article prose

# chrome by tag or aria role
CHROME_SELECTORS = [
    "nav",
    "[role=navigation]",
    "[role=banner]",
    "[role=contentinfo]",
    "[role=complementary]",
    "[role=search]",
    "[aria-label*=navigation i]",
    "[aria-label*=breadcrumb i]",
]

# chrome by name, matched as a whole word against class and id.
#
# NB: no bare "comment" in here. On link aggregators and journal sites the comment thread
# *is* the article the entry points at -- stripping it took 38k characters off a Hacker
# News discussion during testing. Only unambiguous third party widgets are listed.
CHROME_WORDS = re.compile(
    r"(?:^|[-_\s])("
    r"nav|navbar|navigation|menu|menubar|topbar|toolbar|masthead|site-?header|site-?footer"
    r"|sidebar|side-?bar|links-?bar|breadcrumbs?|skip-?link|screen-?reader-?text"
    r"|social|share|sharing|subscribe|newsletter|signup|follow-?us"
    r"|disqus|livefyre|isso-thread|related-?posts?|recirc|more-?from|read-?next"
    r"|cookie|gdpr|consent|banner|promo|advert|advertisement"
    r")(?:[-_\s]|$)",
    re.I,
)

# Sign-offs appended below the article: subscribe pitches, tip jars, affiliate notices.
APPEAL_RE = re.compile(
    r"(consider (?:supporting|subscribing)|support (?:my|our|us|this)"
    r"|subscrib\w+ (?:here|to|for)|you can subscribe|email updates about"
    r"|thank you for (?:visiting|reading)|if you (?:enjoyed|liked|appreciate)"
    r"|buy me a|patreon|ko-?fi|paypal|tip jar|affiliate link"
    r"|respects your privacy|preview of a related post|follow me on)",
    re.I,
)

# Widgets that arrive as a couple of words with no punctuation.
WIDGET_RE = re.compile(r"^(no posts|share|leave a comment|copy as / view markdown|subscribe)$", re.I)

BLOCK_TAGS = {"p", "div", "ul", "ol", "nav", "h1", "h2", "h3", "h4", "header", "footer", "aside", "section", "form"}
TRAILING_WINDOW = 5
APPEAL_MAX_CHARS = 500


def _text(node):
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def _has_prose(node):
    "True if anything inside holds enough continuous text to be part of the article."
    for child in node.find_all(["p", "article", "section", "li", "blockquote", "pre", "td"]):
        if len(_text(child)) >= PROSE_MIN:
            return True
    return len(_text(node)) >= PROSE_MIN * 3  # a long unstructured blob is probably content


def _top_level_blocks(soup):
    "The article's own blocks, past whatever wrapper divs readability nested it in."
    root = soup.body or soup
    while True:
        children = [c for c in root.find_all(recursive=False) if c.name]
        if len(children) == 1 and children[0].name in ("div", "section", "article"):
            root = children[0]
            continue
        break
    return [c for c in root.find_all(recursive=False) if c.name in BLOCK_TAGS]


def strip_hidden(soup):
    """
    Remove elements the page itself marks as hidden.

    Readability only checks the inline style attribute and the hidden attribute, so it
    can't see a `.hidden{display:none}` rule from an external stylesheet. inquirer.com
    ends its pages with a 12KB `<div class="hidden">` of escaped configuration json, which
    readability duly wrapped in a <p> and appended to the article.

    Guarded against pages that hide their whole shell and reveal it on hydration: if an
    element holds most of the document's text it is the page, not a hidden widget.
    """
    body = soup.body or soup
    total = len(_text(body))
    removed = 0

    for node in soup.select("[hidden], .hidden"):
        if node.parent is None:
            continue
        if total and len(_text(node)) > 0.5 * total:
            continue  # this is the page itself, hidden until hydration
        node.decompose()
        removed += 1

    return removed


def unhide_wrapper(soup):
    """
    Drop inline visibility/display styles that hide an entire server-rendered page.

    Gatsby (and other frameworks) wrap the whole SSR shell in
    `<div style="visibility:hidden">` and flip it visible on hydration. Readability's
    isProbablyVisible() drops those nodes, so the article vanishes and it returns null.
    Only ever touches a wrapper that holds most of the page's text, and only as a retry
    after the normal pass has already come back empty.
    """
    body = soup.body or soup
    total = len(_text(body))
    if not total:
        return 0

    changed = 0
    for node in soup.select('[style*="visibility"], [style*="display"]'):
        style = node.get("style") or ""
        if not re.search(r"(visibility\s*:\s*hidden|display\s*:\s*none)", style, re.I):
            continue
        if len(_text(node)) < 0.5 * total:
            continue  # a genuinely hidden widget, leave it hidden
        node["style"] = re.sub(r"(visibility\s*:\s*hidden|display\s*:\s*none)\s*;?", "", style, flags=re.I)
        changed += 1

    return changed


def content_from_metadata(html):
    """
    Last resort: pull the text a page publishes about itself.

    Client rendered pages (mastodon and threads permalinks, say) ship no prose at all --
    readability sees an empty react shell and returns null. But the post text is usually
    right there in the page's own structured data, which is what other clients render
    from. Better a correct short post than an empty reader.
    """
    soup = BeautifulSoup(html, "lxml")

    import json as _json

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
        except Exception:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            for key in ("articleBody", "text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value if "<" in value else f"<p>{value}</p>"

    meta = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    if meta and (meta.get("content") or "").strip():
        return f"<p>{meta['content'].strip()}</p>"

    return None


def strip_chrome(soup, extra_selectors=None):
    """
    Remove site chrome from a page before readability scores it.

    Only removes elements with no prose inside them, so a false positive costs a stray
    link or heading rather than a paragraph. `extra_selectors` comes from a site rule for
    the sites whose chrome carries no recognisable markup at all.
    """
    removed = 0

    for selector in list(CHROME_SELECTORS) + list(extra_selectors or []):
        try:
            matches = soup.select(selector)
        except Exception:
            continue  # a bad selector in a site rule shouldn't break extraction
        for node in matches:
            if node.parent is None or _has_prose(node):
                continue
            node.decompose()
            removed += 1

    for node in soup.find_all(True):
        if node.parent is None or node.name in ("html", "body", "head"):
            continue
        names = " ".join(node.get("class") or []) + " " + (node.get("id") or "")
        if not names.strip() or not CHROME_WORDS.search(names):
            continue
        if _has_prose(node):
            continue
        node.decompose()
        removed += 1

    return removed


def strip_trailing_appeals(soup):
    """
    Drop sign-off blocks that follow the end of the article.

    Walks backwards from the last block and stops at the first one that reads like prose
    or is a heading, so this can only remove material sitting past the article proper.
    """
    blocks = _top_level_blocks(soup)
    removed = 0

    for node in reversed(blocks[-TRAILING_WINDOW:] if len(blocks) > 1 else []):
        text = _text(node)
        if node.name in ("h1", "h2", "h3", "h4"):
            break  # a heading belongs to the article, and so does everything above it
        is_widget = bool(WIDGET_RE.match(text)) or len(text) < 25
        is_appeal = len(text) <= APPEAL_MAX_CHARS and bool(APPEAL_RE.search(text))
        if not (is_widget or is_appeal):
            break
        node.decompose()
        removed += 1

    return removed


def clean_source(html, rule=None):
    "Prepare fetched page html for readability. Returns bytes."
    soup = BeautifulSoup(html, "lxml")
    strip_hidden(soup)
    strip_chrome(soup, extra_selectors=rule.strip if rule else None)

    if rule and rule.content:
        picked = soup.select(rule.content)
        if picked:
            # a site rule naming the article body outright, for pages readability can't score
            return "".join(str(node) for node in picked).encode()

    return str(soup).encode()


def clean_article(content_html):
    "Tidy the html readability produced. Returns a string."
    if not content_html:
        return content_html
    soup = BeautifulSoup(content_html, "lxml")
    strip_trailing_appeals(soup)
    return str(soup)
