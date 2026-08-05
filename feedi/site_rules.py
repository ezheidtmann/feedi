"""
Per site overrides for fetching and extracting articles.

Most sites need nothing here: the generic path in article_clean.py handles them. A rule
earns its place when a site is broken in a way no general heuristic can fix safely --
it refuses feedi's user agent, it hides the article behind a url variant, or its chrome
carries no markup a heuristic could recognise.

Each rule may set:

  user_agent  what to send when fetching from this site
  url_sub     (pattern, replacement) regex rewrite of the article url
  strip       css selectors removed before readability runs
  content     css selector for the article body, bypassing readability's scoring

Keep `content` rules rare: they opt the site out of readability entirely, so they break
silently when the site is redesigned. Prefer `strip`.

Rules match a domain and all of its subdomains, so "substack.com" covers every
publication hosted there.
"""

import urllib.parse

# The conventional crawler shape. Still names feedi and links to the project -- it is not
# browser impersonation -- but it is the form user-agent filters are written to recognise.
# Only for sites that refuse feedi's plainer default: applying it globally cost xeiaso.net
# and lore.kernel.org most of their content, because they read it as a bot.
CRAWLER_USER_AGENT = "Mozilla/5.0 (compatible; feedi/0.1.0; +https://github.com/facundoolano/feedi)"

# A current desktop Chrome, for sites that serve nothing to anything self-identifying.
# Prefer CRAWLER_USER_AGENT: impersonating a browser version means owning its expiry.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


class SiteRule:
    def __init__(self, *domains, user_agent=None, url_sub=None, strip=None, content=None, note=None):
        self.domains = domains
        self.user_agent = user_agent
        self.url_sub = url_sub
        self.strip = strip
        self.content = content
        self.note = note

    def rewrite(self, url):
        if not self.url_sub:
            return url
        import re

        pattern, replacement = self.url_sub
        return re.sub(pattern, replacement, url)

    def headers(self):
        return {"User-Agent": self.user_agent} if self.user_agent else None

    def __repr__(self):
        return f"<SiteRule {'/'.join(self.domains)}>"


# Populated from measurements over the feeds this reader actually follows; each entry
# notes what it fixes so a future reader can tell whether it is still needed.
RULES = [
    SiteRule(
        "utcc.utoronto.ca",
        user_agent=CRAWLER_USER_AGENT,
        note="answers a too-generic agent with HTTP 200 and a 1.7KB 'you're using a tool "
        "with a too-generic User-Agent' page, which we extracted and stored as the "
        "article -- the reader showed the block page under the post's title. Wants the "
        "conventional crawler shape; do NOT give it a browser agent, it rejects Chrome/127 "
        "as too old and that becomes a maintenance treadmill",
    ),
    SiteRule(
        "gilesthomas.com",
        strip=[".site-header", ".tagline", ".links-bar"],
        note="no semantic markup anywhere: nav, article and footer share one div.content, "
        "so class names are the only handle on the menu and tagline",
    ),
    SiteRule(
        "mjg59.dreamwidth.org",
        strip=[".comment-wrapper"],
        note="short posts score lower than the longest reader comment, so readability "
        "picked a commenter's words and showed them under the post's title. Comments are "
        "only stripped here, never generically -- elsewhere they are often the content",
    ),
    SiteRule(
        "huggingface.co",
        strip=['.blog-content a[href="/blog"]'],
        note="a 'Back to Articles' breadcrumb sits inside the article container itself",
    ),
    SiteRule(
        "construction-physics.com",
        content=".available-content",
        note="readability drops this Substack's headings, captions and footnotes; the "
        "post container holds exactly the article",
    ),
    SiteRule(
        "dfarq.homeip.net",
        strip=[".saboxplugin-wrap"],
        note="author bio box appended to every post",
    ),
]


def _host(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def for_url(url):
    "Return the rule matching this url's host (or any parent domain), or None."
    if not url:
        return None
    host = _host(url)
    if not host:
        return None

    for rule in RULES:
        for domain in rule.domains:
            domain = domain.lower()
            if host == domain or host.endswith("." + domain):
                return rule
    return None
