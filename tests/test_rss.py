from feedi.parsers import rss
from tests.conftest import mock_request

FEED_URL = "https://daringfireball.net/feeds/main"

# The shape daringfireball.net publishes for a "linked list" post: the link points at the
# article being commented on, while the post itself --the summary-- lives at the permalink
# published as a rel="related" link.
LINKED_LIST_ITEM = {
    "id": "tag:daringfireball.net,2026:/linked//6.43436",
    "title": "Trump Declares That Lake Ontario Is Now 'Lake America'",
    "link": "https://www.notus.org/trump-white-house/lake-america-ontario",
    "links": [
        {
            "rel": "alternate",
            "type": "text/html",
            "href": "https://www.notus.org/trump-white-house/lake-america-ontario",
        },
        {"rel": "shorturl", "type": "text/html", "href": "http://df4.us/xik"},
        {
            "rel": "related",
            "type": "text/html",
            "href": "https://daringfireball.net/linked/2026/08/28/trump-lake-ontario",
        },
    ],
    "summary": "<p>Jackie Llanos and Jenna Monnin, reporting for NOTUS:</p><blockquote><p>Trump "
    "signed an executive order meant to rename Lake Ontario.</p></blockquote><p>Those who deny "
    "that he's a mad king slipping ever deeper into dementia might say, well, he's joking.</p>",
}

# An article of Gruber's own: no separate permalink, the link is the article.
ARTICLE_ITEM = {
    "id": "tag:daringfireball.net,2026://1.43421",
    "title": "★ Memory and Storage Configurations for the New Mac Minis",
    "link": "https://daringfireball.net/2026/08/configurations_and_pricing",
    "links": [
        {
            "rel": "alternate",
            "type": "text/html",
            "href": "https://daringfireball.net/2026/08/configurations_and_pricing",
        },
        {"rel": "shorturl", "type": "text/html", "href": "http://df4.us/xic"},
    ],
    "summary": "<p>Apple's pricing for the new machines.</p>",
}


def df_parser():
    return rss.DaringFireballParser("daringfireball.net", FEED_URL, None, 10)


def test_daring_fireball_feed_gets_its_own_parser():
    compatible = [cls for cls in rss.RSSParser.__subclasses__() if cls.is_compatible(FEED_URL)]
    assert compatible == [rss.DaringFireballParser]


def test_linked_list_post_is_read_at_its_permalink():
    parser = df_parser()

    # the reader has to show Gruber's post, not the article he's commenting on
    assert (
        parser.parse_content_url(LINKED_LIST_ITEM) == "https://daringfireball.net/linked/2026/08/28/trump-lake-ontario"
    )
    assert parser.parse_content_full(LINKED_LIST_ITEM) == LINKED_LIST_ITEM["summary"]

    # the article he links to is still one click away
    assert parser.parse_target_url(LINKED_LIST_ITEM) == "https://www.notus.org/trump-white-house/lake-america-ontario"


def test_linked_list_preview_and_reader_show_the_same_post():
    parser = df_parser()

    preview = parser.parse_content_short(LINKED_LIST_ITEM)
    assert "mad king" in preview
    assert "mad king" in parser.parse_content_full(LINKED_LIST_ITEM)


def test_article_is_read_at_its_own_url():
    parser = df_parser()

    assert parser.parse_content_url(ARTICLE_ITEM) == ARTICLE_ITEM["link"]
    assert parser.parse_target_url(ARTICLE_ITEM) == ARTICLE_ITEM["link"]
    # nothing to save the reader from scraping the article page
    assert parser.parse_content_full(ARTICLE_ITEM) is None


def test_preview_image_comes_from_the_linked_article(app):
    mock_request(
        LINKED_LIST_ITEM["link"],
        body='<html><head><meta property="og:image" content="https://static.notus.org/lake.jpg"></head></html>',
    )
    mock_request(
        "https://daringfireball.net/linked/2026/08/28/trump-lake-ontario",
        body='<html><head><meta property="og:image" content="https://daringfireball.net/graphics/df-wide-card.png"></head></html>',
    )

    # the summary of this one has no image of its own to use as a preview
    item = dict(LINKED_LIST_ITEM, summary="<p>Reporting for NOTUS.</p>")
    assert df_parser().parse_media_url(item) == "https://static.notus.org/lake.jpg"
