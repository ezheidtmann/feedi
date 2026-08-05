"""
Publication-date extraction for scraped articles.

readability only looks at JSON-LD `datePublished` plus two meta tags, so a lot of sites
that do state a publication date come back from it with none. This module takes a second
pass over the same HTML with a wider net: JSON-LD anywhere in the document, the meta names
publishers actually use, `<time>` elements, and dates embedded in the url. Sites that put
their date somewhere none of that reaches get an explicit rule in SITE_RULES.
"""

import datetime
import json
import logging
import re
import urllib.parse

import dateparser
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

# A date outside this range isn't a publication date, it's an artifact: an unrendered
# template placeholder, a copyright year, a 1970 epoch default, a badly parsed number.
EARLIEST_DATE = datetime.datetime(1990, 1, 1)
# Publishers in timezones ahead of UTC legitimately date today's article "tomorrow".
FUTURE_TOLERANCE = datetime.timedelta(days=2)

# Meta tag names/properties that carry a publication date, best first. Matched
# case-insensitively against the name, property and itemprop attributes.
PUBLISHED_META = [
    "article:published_time",
    "og:article:published_time",
    "article:published",
    "articlepublished",
    "parsely-pub-date",
    "sailthru.date",
    "citation_publication_date",
    "citation_date",
    "datepublished",
    "dc.date.issued",
    "dcterms.issued",
    "dcterms.date",
    "dc.date",
    "date",
    "publish-date",
    "publishdate",
    "publication_date",
    "pubdate",
    "post_date",
    "timestamp",
    "displaydate",
]

# Only consulted when nothing above matched: a modified date is not the publication date,
# but on the sites that expose nothing else it is almost always the same day.
MODIFIED_META = [
    "article:modified_time",
    "og:updated_time",
    "datemodified",
    "last-modified",
]

# JSON-LD @type values whose datePublished describes the article rather than something
# embedded in the page (a comment, a related item, the site's organization record).
ARTICLE_LD_TYPES = {
    "article",
    "newsarticle",
    "blogposting",
    "techarticle",
    "scholarlyarticle",
    "medicalscholarlyarticle",
    "advertisercontentarticle",
    "satiricalarticle",
    "analysisnewsarticle",
    "backgroundnewsarticle",
    "opinionnewsarticle",
    "reportagenewsarticle",
    "reviewnewsarticle",
    "report",
    "review",
    "liveblogposting",
    "socialmediaposting",
    "discussionforumposting",
    "videoobject",
    "podcastepisode",
    "webpage",
    "itempage",
    "articlepage",
    "creativework",
}

LD_PUBLISHED_KEYS = ["datepublished", "datecreated", "uploaddate", "published", "publisheddate"]
LD_MODIFIED_KEYS = ["datemodified", "dateupdated"]

# CSS selectors for elements that hold a date, best first. Anything matching these is
# far more likely to be the publication date than a bare `<time>` somewhere on the page.
DATE_SELECTORS = [
    "[itemprop~=datePublished]",
    "time[pubdate]",
    "time.published",
    "time.entry-date",
    "time.post-date",
    ".published time",
    ".post-date time",
    ".entry-date time",
    ".byline time",
    ".dateline time",
    "article time",
    "header time",
    # a timestamp left for the site's own javascript to render, which the digest never runs
    "[data-timestamp]",
]

# Attributes that carry a machine-readable date on an element that shows one.
DATE_ATTRS = ["datetime", "content", "data-timestamp", "data-datetime", "data-date", "title"]

# Only a date the url states to the day: half the blogs we read are under /YYYY/MM/, and
# guessing the 1st of that month is off by two weeks on average — worse than no date,
# and worse than the date the feed itself reported.
URL_DATE_PATTERNS = [
    re.compile(r"/(?P<year>19\d{2}|20\d{2})/(?P<month>0?[1-9]|1[0-2])/(?P<day>0?[1-9]|[12]\d|3[01])(?:/|-|_)"),
    re.compile(r"[/-](?P<year>19\d{2}|20\d{2})-(?P<month>0[1-9]|1[0-2])-(?P<day>0[1-9]|[12]\d|3[01])(?:[/-]|$)"),
]

# Written dates as a reader sees them, day precision only: a bare "March 2020" in the page
# text is as likely to be an archive link or a sentence as it is the publication date.
_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?"
    r"|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
TEXT_DATE = re.compile(
    r"\b(?:"
    r"(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}"  # 2026-07-21
    rf"|(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+(?:19|20)\d{{2}}"  # July 22nd, 2026
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\.?,?\s+(?:19|20)\d{{2}}"  # 24 May 2026
    r")\b",
    re.I,
)

# A publication date is stated on its own ("Published on 18 June 2026", "Chris Siebenmann,
# 2026-04-18"), so anything longer than a label is prose that happens to mention a date.
TEXT_DATE_MAX_LEN = 80

# Text inside these never states when the article was published: it's navigation, a quoted
# or embedded document, or a code sample.
TEXT_SKIP_CONTAINERS = {"nav", "footer", "aside", "form", "svg", "figure", "blockquote", "table", "code", "pre"}

# Elements whose name or class says the text in them is a date rather than page furniture.
TEXT_DATEISH_TAGS = {"time", "address", "small"}
TEXT_DATEISH_ATTRS = re.compile(r"date|publish|posted|post-meta|postmeta|byline|meta|timestamp", re.I)


def parse(value):
    """
    Turn a date found in a page into a naive UTC datetime, or None if it can't be read
    or lands outside the range a publication date can plausibly occupy.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        dt = value
    elif isinstance(value, datetime.date):
        dt = datetime.datetime(value.year, value.month, value.day)
    else:
        value = str(value).strip()
        if not value:
            return None
        dt = _parse_string(value)

    if dt is None:
        return None

    if dt.tzinfo:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    if dt < EARLIEST_DATE or dt > datetime.datetime.utcnow() + FUTURE_TOLERANCE:
        logger.debug("discarding out of range date %s", dt)
        return None

    return dt


def _parse_string(value):
    # A value stating only a year or a year and month is not a publication date: read
    # literally it would put every such article on the 1st, off by weeks.
    if re.fullmatch(r"(19|20)\d{2}(?:[-/]\d{1,2})?", value):
        return None

    # Most of what we find is already ISO 8601; try that before dateparser, which is
    # comparatively slow and occasionally too creative with ambiguous input. isoparse
    # rather than datetime.fromisoformat, which before python 3.11 rejects the "+0000"
    # and "Z" spellings of the offset that plenty of publishers emit.
    try:
        return dateutil_parser.isoparse(value)
    except (ValueError, OverflowError):
        pass

    # A bare unix timestamp (seconds or milliseconds), as some CMSs emit.
    if re.fullmatch(r"\d{9,13}", value):
        seconds = int(value) / 1000 if len(value) > 10 else int(value)
        try:
            return datetime.datetime.utcfromtimestamp(seconds)
        except (ValueError, OverflowError):
            return None

    try:
        # DMY: the sites we read that use ambiguous numeric dates are more often
        # non-US than not, and unambiguous formats are unaffected by the setting.
        # RETURN_AS_TIMEZONE_AWARE is deliberately left alone: setting it False makes
        # dateparser return None for any input that does carry an offset. `parse`
        # normalizes to naive UTC afterwards.
        return dateparser.parse(value, settings={"DATE_ORDER": "DMY"})
    except Exception:
        logger.debug("could not parse date %r", value)
        return None


#
# Per-site rules
#

SITE_RULES = {}


def site_rule(*domains):
    """
    Register a function returning the publication date for pages of the given domains,
    for sites whose date none of the generic strategies can reach. The function takes
    (soup, url) and returns a date, a datetime, a parseable string, or None.
    """

    def decorator(fn):
        for domain in domains:
            SITE_RULES[domain] = fn
        return fn

    return decorator


def _site_rule_for(url):
    if not url:
        return None
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    host = host.removeprefix("www.")
    while host:
        if host in SITE_RULES:
            return SITE_RULES[host]
        _, _, host = host.partition(".")
    return None


#
# Extraction strategies
#


def _from_site_rule(soup, url):
    rule = _site_rule_for(url)
    if not rule:
        return None
    try:
        return rule(soup, url)
    except Exception:
        logger.exception("site date rule failed for %s", url)
        return None


def _iter_ld_nodes(soup):
    "Yield every object inside the page's ld+json blocks, nested ones included."
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        raw = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", raw.strip())
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            logger.debug("unparseable ld+json block")
            continue

        stack = [data]
        while stack:
            node = stack.pop(0)
            if isinstance(node, dict):
                yield node
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)


def _ld_types(node):
    types = node.get("@type") or node.get("type") or []
    if isinstance(types, str):
        types = [types]
    return {str(t).lower() for t in types if isinstance(t, (str, int))}


def _ld_value(node, keys):
    for key, value in node.items():
        if str(key).lower() in keys:
            # some publishers nest it, e.g. {"datePublished": {"@value": "..."}}
            if isinstance(value, dict):
                value = value.get("@value")
            if isinstance(value, str):
                return value
    return None


def _from_json_ld(soup, keys=LD_PUBLISHED_KEYS):
    """
    Search the page's JSON-LD for a date. Nodes typed as an article win over any other
    node that happens to carry a date, so a comment or a related-item block can't
    outrank the article itself.
    """
    fallback = None
    for node in _iter_ld_nodes(soup):
        value = _ld_value(node, keys)
        if not value:
            continue
        if _ld_types(node) & ARTICLE_LD_TYPES:
            return value
        fallback = fallback or value
    return fallback


def _meta_values(soup):
    "Map every meta tag's name/property/itemprop (lowercased) to its content."
    values = {}
    for tag in soup.find_all("meta", content=True):
        for attr in ("property", "name", "itemprop"):
            key = tag.get(attr)
            if key:
                values.setdefault(str(key).strip().lower(), tag["content"])
    return values


def _from_meta(soup, names=PUBLISHED_META):
    values = _meta_values(soup)
    for name in names:
        if values.get(name):
            return values[name]
    return None


def _looks_like_an_update(element):
    label = " ".join(element.get("class") or []) + " " + element.get_text(" ", strip=True)
    return bool(re.search(r"updat|modif|revis", label, re.I))


def _element_date(element):
    "Read a date off an element: a machine-readable attribute if it has one, else its text."
    for attr in DATE_ATTRS:
        value = element.get(attr)
        if value and parse(value):
            return value
    text = element.get_text(" ", strip=True)
    if text and len(text) <= TEXT_DATE_MAX_LEN and parse(text):
        return text
    return None


def _from_elements(soup):
    for selector in DATE_SELECTORS:
        try:
            elements = soup.select(selector)
        except Exception:
            # soupsieve rejects the odd selector depending on the parse tree
            continue
        for element in elements:
            if _looks_like_an_update(element):
                continue
            value = _element_date(element)
            if value:
                return value

    # Last resort within the document: the first <time> anywhere. Plenty of hand-written
    # blogs use one with the date only as text, no datetime attribute.
    for element in soup.find_all("time"):
        if _looks_like_an_update(element):
            continue
        value = _element_date(element)
        if value:
            return value
    return None


def _is_dateish(element):
    "True if the element itself says the text inside it is a date."
    while element is not None and getattr(element, "name", None):
        if element.name in TEXT_DATEISH_TAGS:
            return True
        attrs = " ".join(element.get("class") or []) + " " + (element.get("id") or "")
        if TEXT_DATEISH_ATTRS.search(attrs):
            return True
        element = element.parent
        if element is not None and element.name in ("body", "html", "[document]"):
            break
    return False


def _is_skipped(node):
    for parent in node.parents:
        if parent.name in TEXT_SKIP_CONTAINERS:
            return True
        if parent.name in ("body", "[document]"):
            break
    return False


def _from_text(soup):
    """
    Find the date a reader sees on the page: a lot of hand-rolled blogs print it as plain
    text under the title with no markup saying what it is. Candidates in an element that
    announces itself as a date win; otherwise the first one in the document does, which on
    an article page is the one under the title rather than one further down the body.
    """
    plain = None
    for node in (soup.body or soup).find_all(string=TEXT_DATE):
        text = " ".join(str(node).split())
        if len(text) > TEXT_DATE_MAX_LEN or re.search(r"updat|modif|revis|comment", text, re.I):
            continue
        if _is_skipped(node):
            continue
        value = TEXT_DATE.search(text).group(0)
        if not parse(value):
            continue
        if _is_dateish(node.parent):
            return value
        plain = plain or value
    return plain


def _from_url(url):
    if not url:
        return None
    path = urllib.parse.urlparse(url).path
    for pattern in URL_DATE_PATTERNS:
        match = pattern.search(path)
        if not match:
            continue
        parts = match.groupdict()
        try:
            return datetime.datetime(int(parts["year"]), int(parts["month"]), int(parts.get("day") or 1))
        except ValueError:
            continue
    return None


# Ordered strategies. Each takes (soup, url) and returns something `parse` can read.
STRATEGIES = [
    ("site_rule", _from_site_rule),
    ("json_ld", lambda soup, url: _from_json_ld(soup)),
    ("meta", lambda soup, url: _from_meta(soup)),
    ("element", lambda soup, url: _from_elements(soup)),
    ("url", lambda soup, url: _from_url(url)),
    ("text", lambda soup, url: _from_text(soup)),
    ("json_ld_modified", lambda soup, url: _from_json_ld(soup, LD_MODIFIED_KEYS)),
    ("meta_modified", lambda soup, url: _from_meta(soup, MODIFIED_META)),
]


def from_html(html, url=None, with_source=False):
    """
    Return the publication date of the article in `html` as a naive UTC datetime, or None.
    With `with_source`, return a (date, strategy name) tuple instead, which is what the
    date coverage script reports on.
    """
    soup = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "lxml")
    for name, strategy in STRATEGIES:
        try:
            date = parse(strategy(soup, url))
        except Exception:
            logger.exception("date strategy %s failed for %s", name, url)
            continue
        if date:
            return (date, name) if with_source else date
    return (None, None) if with_source else None


def resolve(known, html=None, url=None):
    """
    Settle on the publication date for an article: whatever the extractor already
    reported if it's usable, otherwise a second pass over the html, otherwise the url.
    """
    date = parse(known)
    if date:
        return date
    if html is not None:
        return from_html(html, url)
    return parse(_from_url(url))
