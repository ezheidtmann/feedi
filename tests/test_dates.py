import datetime

import feedi.dates as dates


def page(head="", body=""):
    return f"<html><head>{head}</head><body>{body}</body></html>"


def test_parse_normalizes_to_naive_utc():
    assert dates.parse("2024-05-12T10:00:00Z") == datetime.datetime(2024, 5, 12, 10, 0)
    assert dates.parse("2024-05-12T10:00:00+05:00") == datetime.datetime(2024, 5, 12, 5, 0)
    assert dates.parse("May 12, 2024") == datetime.datetime(2024, 5, 12)
    assert dates.parse(datetime.date(2024, 5, 12)) == datetime.datetime(2024, 5, 12)


def test_parse_reads_the_offset_spellings_publishers_actually_use():
    "An offset written without a colon is common, and used to be dropped on the floor."
    assert dates.parse("2026-07-30T19:00:00+0000") == datetime.datetime(2026, 7, 30, 19, 0)
    assert dates.parse("2026-07-30T19:00:00-0400") == datetime.datetime(2026, 7, 30, 23, 0)
    assert dates.parse("2026-07-30 19:00:00") == datetime.datetime(2026, 7, 30, 19, 0)
    assert dates.parse("Wed, 30 Jul 2026 19:00:00 GMT") == datetime.datetime(2026, 7, 30, 19, 0)
    # a unix timestamp, in seconds or milliseconds
    assert dates.parse("1715515200") == datetime.datetime(2024, 5, 12, 12, 0)
    assert dates.parse("1715515200000") == datetime.datetime(2024, 5, 12, 12, 0)


def test_parse_rejects_dates_with_no_day():
    "Read literally, a bare year or year-month would date every such article to the 1st."
    assert dates.parse("2024") is None
    assert dates.parse("2024-05") is None
    assert dates.from_html(page(head='<meta name="date" content="2024">')) is None


def test_parse_rejects_implausible_dates():
    "A date far in the past or the future is a template artifact, not a publication date."
    assert dates.parse("1970-01-01T00:00:00Z") is None
    assert dates.parse("0001-01-01") is None
    assert dates.parse((datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat()) is None
    assert dates.parse("") is None
    assert dates.parse("not a date") is None


def test_meta_tags_beyond_the_two_readability_knows():
    """
    readability only reads article:published_time and parsely-pub-date, so anything
    else on this list used to leave the article undated.
    """
    for tag in [
        '<meta property="og:article:published_time" content="2021-03-04T05:06:07Z">',
        '<meta name="DC.date.issued" content="2021-03-04">',
        '<meta name="publish-date" content="2021-03-04">',
        '<meta itemprop="datePublished" content="2021-03-04">',
        '<meta name="sailthru.date" content="2021-03-04 00:00:00">',
    ]:
        assert dates.from_html(page(head=tag)) == datetime.datetime(2021, 3, 4, 5, 6, 7) or dates.from_html(
            page(head=tag)
        ) == datetime.datetime(2021, 3, 4), tag


def test_json_ld_in_graph_and_with_type_lists():
    "readability bails on @graph entries typed with a list, which is a common shape."
    head = """<script type="application/ld+json">
    {"@context": "https://schema.org",
     "@graph": [{"@type": "WebSite", "name": "a blog"},
                {"@type": ["Article", "BlogPosting"], "datePublished": "2022-08-09T12:00:00Z"}]}
    </script>"""
    assert dates.from_html(page(head=head)) == datetime.datetime(2022, 8, 9, 12, 0)


def test_json_ld_prefers_the_article_over_other_dated_nodes():
    "A comment's date must not outrank the article's."
    head = """<script type="application/ld+json">
    [{"@type": "Comment", "datePublished": "2023-01-31"},
     {"@type": "BlogPosting", "datePublished": "2023-01-05"}]
    </script>"""
    assert dates.from_html(page(head=head)) == datetime.datetime(2023, 1, 5)


def test_time_elements():
    assert dates.from_html(page(body='<time pubdate datetime="2020-02-02">Feb 2</time>')) == datetime.datetime(
        2020, 2, 2
    )
    assert dates.from_html(
        page(body='<article><time datetime="2020-02-02T09:00:00Z">Feb 2</time></article>')
    ) == datetime.datetime(2020, 2, 2, 9, 0)
    # a date only readable as text, which is how plenty of blog templates render it
    assert dates.from_html(page(body='<span itemprop="datePublished">3 February 2020</span>')) == datetime.datetime(
        2020, 2, 3
    )


def test_time_element_labelled_as_an_update_is_not_the_publication_date():
    body = '<div><time class="updated" datetime="2024-01-01">Updated</time></div>'
    assert dates.from_html(body) is None


def test_url_dates():
    assert dates.from_html(page(), "https://blog.example/2019/09/09/a-post") == datetime.datetime(2019, 9, 9)
    assert dates.from_html(page(), "https://blog.example/posts/2019-09-09-a-post") == datetime.datetime(2019, 9, 9)
    # version numbers and id-looking paths must not read as dates
    assert dates.from_html(page(), "https://example.com/docs/1999/") is None
    assert dates.from_html(page(), "https://example.com/p/2024/13/40/x") is None


def test_month_precision_url_is_not_a_date():
    """
    /YYYY/MM/ says nothing about the day, and calling it the 1st is off by half a month
    on average — worse than reporting no date and falling back to the feed's own.
    """
    assert dates.from_html(page(), "https://blog.example/2019/09/a-post") is None


def test_dates_written_as_plain_text():
    "The shape a hand-written blog takes: a date under the title, in no particular markup."
    for body, expected in [
        ('<h1>A post</h1><p class="mt-2">January 18, 2026</p><p>Body text.</p>', datetime.datetime(2026, 1, 18)),
        ('<span class="post-meta">July 29, 2026</span>', datetime.datetime(2026, 7, 29)),
        ("<div>Published on 18 June 2026.</div>", datetime.datetime(2026, 6, 18)),
        ("<address>Chris Siebenmann, 2026-04-18</address>", datetime.datetime(2026, 4, 18)),
        ("<small>Wednesday, July 22nd 2026</small>", datetime.datetime(2026, 7, 22)),
        ("<p>2 February 2015 / 1,800 words</p>", datetime.datetime(2015, 2, 2)),
    ]:
        assert dates.from_html(page(body=body)) == expected, body


def test_text_dates_only_where_they_mean_a_publication_date():
    # a date inside a sentence is not a dateline
    prose = "<p>I first ran into this on July 4, 2019 while debugging a release, and it took all week.</p>"
    assert dates.from_html(page(body=prose)) is None
    # nor is one in a quote, an embedded document or the page furniture
    assert dates.from_html(page(body="<blockquote>March 3, 2011</blockquote>")) is None
    assert dates.from_html(page(body="<footer>March 3, 2011</footer>")) is None
    assert dates.from_html(page(body="<pre>2011-03-03</pre>")) is None
    # month precision is too coarse to trust as a publication date
    assert dates.from_html(page(body="<p>Posted in March 2020.</p>")) is None


def test_element_dates_left_for_javascript_to_render():
    body = '<span class="flask-moment" data-timestamp="2026-06-12T09:20:39Z" style="display: none"></span>'
    assert dates.from_html(page(body=body)) == datetime.datetime(2026, 6, 12, 9, 20, 39)


def test_page_date_wins_over_url_date():
    head = '<meta property="article:published_time" content="2019-09-11">'
    assert dates.from_html(page(head=head), "https://blog.example/2019/09/09/a-post") == datetime.datetime(2019, 9, 11)


def test_modified_date_only_as_a_last_resort():
    head = '<meta property="article:modified_time" content="2020-06-07">'
    assert dates.from_html(page(head=head)) == datetime.datetime(2020, 6, 7)

    both = head + '<meta property="article:published_time" content="2020-06-01">'
    assert dates.from_html(page(head=both)) == datetime.datetime(2020, 6, 1)


def test_from_html_reports_which_strategy_found_the_date():
    head = '<meta property="article:published_time" content="2020-06-01">'
    assert dates.from_html(page(head=head), with_source=True) == (datetime.datetime(2020, 6, 1), "meta")
    assert dates.from_html(page(), "http://x.com/a", with_source=True) == (None, None)


def test_resolve_falls_back_from_a_bad_extractor_value():
    html = page(head='<meta property="article:published_time" content="2020-06-01">')
    assert dates.resolve("2018-04-05T00:00:00Z", html) == datetime.datetime(2018, 4, 5)
    # readability picked up a placeholder; the page still knows better
    assert dates.resolve("1970-01-01T00:00:00Z", html) == datetime.datetime(2020, 6, 1)
    assert dates.resolve(None, page(), "http://x.com/2017/07/07/a") == datetime.datetime(2017, 7, 7)


def test_site_rules_take_precedence(monkeypatch):
    monkeypatch.setitem(dates.SITE_RULES, "example.com", lambda soup, url: "2015-05-05")
    head = '<meta property="article:published_time" content="2020-06-01">'
    assert dates.from_html(page(head=head), "https://www.example.com/a") == datetime.datetime(2015, 5, 5)
    assert dates.from_html(page(head=head), "https://sub.example.com/a") == datetime.datetime(2015, 5, 5)
    assert dates.from_html(page(head=head), "https://other.com/a") == datetime.datetime(2020, 6, 1)


def test_broken_site_rule_falls_through(monkeypatch):
    def boom(soup, url):
        raise ValueError("nope")

    monkeypatch.setitem(dates.SITE_RULES, "example.com", boom)
    head = '<meta property="article:published_time" content="2020-06-01">'
    assert dates.from_html(page(head=head), "https://example.com/a") == datetime.datetime(2020, 6, 1)
