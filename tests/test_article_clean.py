from unittest import mock

import httpretty
from bs4 import BeautifulSoup

import feedi.scraping as scraping
from feedi import article_clean, site_rules
from tests.conftest import mock_request

PROSE = (
    "The extended train ran for forty hours before it crashed, which was long enough to "
    "produce a loss curve worth looking at and short enough that I still remembered what "
    "I had changed since the previous run. "
)


def soup_of(html):
    return BeautifulSoup(html, "lxml")


def text_of(soup):
    return " ".join(soup.get_text(" ").split())


def test_strips_a_menu_that_shares_a_container_with_the_article():
    """
    The shape that started this: no semantic markup anywhere, so the site's menu sits in
    the same div as the article and readability keeps it. Only the class name gives it away.
    """
    soup = soup_of(f"""
        <body><div class="content">
          <div class="links-bar"><a href="/a">Archives</a><a href="/c">Categories</a><a href="/b">Blogroll</a></div>
          <p>{PROSE}</p>
        </div></body>
    """)

    article_clean.strip_chrome(soup)

    assert "Archives" not in text_of(soup)
    assert "Blogroll" not in text_of(soup)
    assert PROSE.strip() in text_of(soup)


def test_keeps_comment_threads():
    """
    On link aggregators and journal sites the comment thread IS the article the entry
    points at. An earlier version of this stripped anything class~="comment" and took
    38k characters off a Hacker News discussion.
    """
    soup = soup_of(f"""
        <body>
          <div class="comment-tree">
            <div class="comment"><p>{PROSE}</p></div>
            <div class="comment"><p>Short but real reply.</p></div>
          </div>
        </body>
    """)

    article_clean.strip_chrome(soup)

    assert PROSE.strip() in text_of(soup)
    assert "Short but real reply." in text_of(soup)


def test_keeps_chrome_named_elements_that_hold_prose():
    "A <div class='post-header'> is chrome by name but may carry the article's opening."
    soup = soup_of(f'<body><div class="post-header"><p>{PROSE}</p></div></body>')

    article_clean.strip_chrome(soup)

    assert PROSE.strip() in text_of(soup)


def test_strips_semantic_chrome():
    soup = soup_of(f"""
        <body>
          <nav><a href="/">Home</a><a href="/about">About</a></nav>
          <div role="complementary"><a href="/feed">Subscribe by RSS</a></div>
          <p>{PROSE}</p>
          <footer role="contentinfo">All rights reserved</footer>
        </body>
    """)

    article_clean.strip_chrome(soup)
    text = text_of(soup)

    assert "Home" not in text
    assert "Subscribe by RSS" not in text
    assert "All rights reserved" not in text
    assert PROSE.strip() in text


def test_strips_trailing_subscribe_pitch():
    soup = soup_of(f"""
        <body><div>
          <p>{PROSE}</p>
          <p>Thank you for visiting my blog! If you enjoyed this article, please consider
             supporting my work and keeping me caffeinated.</p>
        </div></body>
    """)

    assert article_clean.strip_trailing_appeals(soup) == 1
    assert "caffeinated" not in text_of(soup)
    assert PROSE.strip() in text_of(soup)


def test_trailing_pass_stops_at_the_article():
    "It must never chew upwards past the end of the article into real content."
    soup = soup_of(f"""
        <body><div>
          <p>{PROSE}</p>
          <h2>Notes and references</h2>
          <p>Short closing note.</p>
        </div></body>
    """)

    article_clean.strip_trailing_appeals(soup)
    text = text_of(soup)

    assert "Notes and references" in text, "a heading belongs to the article"
    assert PROSE.strip() in text


def test_appeal_in_the_middle_of_an_article_survives():
    soup = soup_of(f"""
        <body><div>
          <p>{PROSE}</p>
          <p>If you enjoyed this, consider subscribing.</p>
          <p>{PROSE}</p>
        </div></body>
    """)

    article_clean.strip_trailing_appeals(soup)

    assert "consider subscribing" in text_of(soup)


def test_site_rules_match_subdomains():
    rule = site_rules.SiteRule("example.com", user_agent="test-agent")

    with mock.patch.object(site_rules, "RULES", [rule]):
        assert site_rules.for_url("https://example.com/post") is rule
        assert site_rules.for_url("https://blog.example.com/post") is rule
        assert site_rules.for_url("https://notexample.com/post") is None
        assert site_rules.for_url("https://example.com.evil.net/post") is None
        assert site_rules.for_url(None) is None


def test_site_rule_overrides_the_user_agent_for_a_fetch(app):
    "The point of a ua rule: sites that refuse feedi's own agent."
    url = "http://ua-picky.example.com/post"
    mock_request(url, body=f"<html><body><article><p>{PROSE}</p></article></body></html>")
    rule = site_rules.SiteRule("ua-picky.example.com", user_agent="Mozilla/5.0 (pretend browser)")

    with mock.patch.object(site_rules, "RULES", [rule]), app.app_context():
        scraping.extract(url)

    assert httpretty.last_request().headers["User-Agent"] == "Mozilla/5.0 (pretend browser)"


def test_fetches_identify_feedi_without_a_rule(app):
    """
    The default agent uses the "Mozilla/5.0 (compatible; ...)" shape that ua filters
    recognise, but it must still name feedi and link to the project rather than
    impersonate a browser.
    """
    url = "http://ordinary.example.com/post"
    mock_request(url, body=f"<html><body><article><p>{PROSE}</p></article></body></html>")

    with mock.patch.object(site_rules, "RULES", []), app.app_context():
        scraping.extract(url)

    agent = httpretty.last_request().headers["User-Agent"]
    assert "feedi/0.1.0" in agent
    assert "github.com/facundoolano/feedi" in agent
    assert "Chrome" not in agent and "Safari" not in agent


def test_site_rule_rewrites_the_url(app):
    "Used for sites that only serve the full article at a print or amp variant."
    mock_request("http://rewrite.example.com/post?print=1", body=f"<html><body><p>{PROSE}</p></body></html>")
    rule = site_rules.SiteRule("rewrite.example.com", url_sub=(r"$", "?print=1"))

    with mock.patch.object(site_rules, "RULES", [rule]), app.app_context():
        scraping.extract("http://rewrite.example.com/post")

    assert httpretty.last_request().path == "/post?print=1"


def test_strips_elements_the_page_hides():
    "inquirer.com ends its pages with 12KB of escaped config json in a .hidden div."
    soup = soup_of(f"""
        <body>
          <p>{PROSE}</p>
          <div class="hidden">{{"ENV":"awVjRlw", "TOKEN":"abc123"}}</div>
          <div hidden>tracking pixel config</div>
        </body>
    """)

    article_clean.strip_hidden(soup)
    text = text_of(soup)

    assert "ENV" not in text
    assert "tracking pixel config" not in text
    assert PROSE.strip() in text


def test_does_not_strip_a_page_that_hides_its_whole_shell():
    "Frameworks hide the server-rendered shell until hydration; that is the page, not a widget."
    soup = soup_of(f'<body><div class="hidden"><article><p>{PROSE}</p></article></div></body>')

    article_clean.strip_hidden(soup)

    assert PROSE.strip() in text_of(soup)


def test_unhides_a_hidden_server_rendered_shell():
    """
    Gatsby wraps the whole SSR shell in visibility:hidden and flips it on hydration.
    Readability drops hidden nodes, finds nothing, and returns null.
    """
    soup = soup_of(f'<body><div style="visibility:hidden"><article><p>{PROSE}</p></article></div></body>')

    assert article_clean.unhide_wrapper(soup) == 1
    assert "visibility:hidden" not in str(soup).replace(" ", "")


def test_unhide_leaves_genuinely_hidden_widgets_alone():
    soup = soup_of(f"""
        <body>
          <article><p>{PROSE}</p></article>
          <div style="display:none">cookie banner copy</div>
        </body>
    """)

    assert article_clean.unhide_wrapper(soup) == 0


def test_metadata_fallback_reads_structured_data():
    "Client-rendered permalinks ship the post only as json-ld or og:description."
    html = """
        <html><head>
          <script type="application/ld+json">
            {"@type": "SocialMediaPosting", "text": "Quiche Browser disables AI overviews by default."}
          </script>
        </head><body><div id="mastodon"></div></body></html>
    """

    assert "Quiche Browser disables AI overviews" in article_clean.content_from_metadata(html)


def test_metadata_fallback_uses_og_description_when_there_is_no_json_ld():
    html = '<html><head><meta property="og:description" content="Why is it always July 17?"></head><body></body></html>'

    assert "Why is it always July 17?" in article_clean.content_from_metadata(html)


def test_extract_recovers_an_article_readability_returns_nothing_for(app):
    "End to end: a hidden SSR shell must come back through the fallback path."
    url = "http://gatsby.example.com/post"
    mock_request(
        url,
        body=f'<html><body><div style="visibility:hidden"><main><article><p>{PROSE}</p>'
        f"<p>{PROSE}</p></article></main></div></body></html>",
    )

    with mock.patch.object(site_rules, "RULES", []), app.app_context():
        article = scraping.extract(url)

    assert PROSE.strip() in " ".join(article["content"].split())
