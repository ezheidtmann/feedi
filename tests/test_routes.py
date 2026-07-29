import datetime as dt
import io
import json
import re
import zipfile
from unittest import mock
from xml.etree import ElementTree as ET

from requests.exceptions import RequestException

from tests.conftest import create_feed, extract_entry_ids, mock_feed, mock_request


def test_feed_add(client):
    feed_domain = "feed1.com"
    response, feed_id = create_feed(
        client,
        feed_domain,
        [
            {"title": "my-first-article", "date": "2023-10-01 00:00Z"},
            {"title": "my-second-article", "date": "2023-10-10 00:00Z"},
        ],
    )

    assert response.status_code == 200
    assert response.request.path == f"/feeds/{feed_id}/entries", "feed submit should redirect to entry list"

    assert "my-first-article" in response.text, "article should be included in entry list"
    assert "my-second-article" in response.text, "article should be included in entry list"
    assert response.text.find("my-second-article") < response.text.find("my-first-article"), (
        "articles should be sorted by publication date"
    )

    # check same entries show up in home feed
    response = client.get("/")
    assert response.status_code == 200

    assert "my-first-article" in response.text, "article should be included in entry list"
    assert "my-second-article" in response.text, "article should be included in entry list"
    assert response.text.find("my-second-article") < response.text.find("my-first-article"), (
        "articles should be sorted by publication date"
    )


def test_folders(client):
    # feed1, feed2 -> folder 1
    create_feed(
        client,
        "feed1.com",
        [{"title": "f1-a1", "date": "2023-10-01 00:00Z"}, {"title": "f1-a2", "date": "2023-10-10 00:00Z"}],
        folder="folder1",
    )

    create_feed(
        client,
        "feed2.com",
        [{"title": "f2-a1", "date": "2023-10-01 00:00Z"}, {"title": "f2-a2", "date": "2023-10-10 00:00Z"}],
        folder="folder1",
    )

    # feed3 -> folder 2
    create_feed(
        client,
        "feed3.com",
        [{"title": "f3-a1", "date": "2023-10-01 00:00Z"}, {"title": "f3-a2", "date": "2023-10-10 00:00Z"}],
        folder="folder2",
    )

    # feed4 -> no folder
    create_feed(
        client,
        "feed4.com",
        [{"title": "f4-a1", "date": "2023-10-01 00:00Z"}, {"title": "f4-a2", "date": "2023-10-10 00:00Z"}],
    )

    response = client.get("/")
    assert all(
        [feed in response.text for feed in ["f1-a1", "f1-a2", "f2-a1", "f2-a2", "f3-a1", "f3-a2", "f4-a1", "f4-a2"]]
    )

    response = client.get("/folder/folder1")
    assert all([feed in response.text for feed in ["f1-a1", "f1-a2", "f2-a1", "f2-a2"]])
    assert all([feed not in response.text for feed in ["f3-a1", "f3-a2", "f4-a1", "f4-a2"]])

    response = client.get("/folder/folder2")
    assert all([feed in response.text for feed in ["f3-a1", "f3-a2"]])
    assert all([feed not in response.text for feed in ["f1-a1", "f1-a2", "f2-a1", "f2-a2", "f4-a1", "f4-a2"]])


def test_home_sorting(client):
    # feed1: 1 post 12 hs ago
    date12h = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)
    create_feed(client, "feed1.com", [{"title": "f1-a1", "date": date12h}])

    # feed2: 20 posts < 12 hs ago
    items = []
    for i in range(1, 21):
        items.append({"title": f"f2-a{i}", "date": date12h + dt.timedelta(hours=1, minutes=i)})
    create_feed(client, "feed2.com", items)

    # home shows f1 post first
    # the rest are in chronological order
    response = client.get("/")
    assert response.text.find("f1-a1") < response.text.find("f2-a20")
    assert response.text.find("f2-a20") < response.text.find("f2-a12")

    # feed3: 1 post 13 hs ago
    date13h = date12h - dt.timedelta(hours=1)
    create_feed(client, "feed3.com", [{"title": "f3-a1", "date": date13h}])

    response = client.get("/")
    assert response.text.find("f1-a1") < response.text.find("f3-a1")
    assert response.text.find("f3-a1") < response.text.find("f2-a13")


def test_home_pagination(app, client):
    now = dt.datetime.now(dt.timezone.utc)
    items = []
    per_page = app.config["ENTRY_PAGE_SIZE"]
    for i in range(0, per_page * 3):
        items.append({"title": f"f1-a{i}", "date": now - dt.timedelta(hours=3, minutes=i)})
    create_feed(client, "feed1.com", items)

    # home includes a first page of results, sorted by pub date
    response = client.get("/")
    assert "f1-a0" in response.text
    assert f"f1-a{per_page - 1}" in response.text
    assert f"f1-a{per_page}" not in response.text
    assert response.text.find("f1-a0") < response.text.find(f"f1-a{per_page - 1}")

    next_page = re.search(r'page=([^&"]+)', response.text).group(1)
    response = client.get(f"/?page={next_page}")
    assert f"f1-a{per_page - 1}" not in response.text
    assert f"f1-a{per_page}" in response.text
    assert f"f1-a{per_page * 2 - 1}" in response.text
    assert f"f1-a{per_page * 2}" not in response.text

    # get home again without page, verify the first page was marked as already seen
    response = client.get("/")
    assert f"f1-a{per_page - 1}" not in response.text
    assert f"f1-a{per_page}" in response.text
    assert f"f1-a{per_page * 2 - 1}" in response.text
    assert f"f1-a{per_page * 2}" not in response.text

    # change settings to include already seen
    response = client.post("/session/hide_seen")
    assert response.status_code == 204

    # get home again, verify first page is included again
    response = client.get("/")
    assert "f1-a0" in response.text
    assert f"f1-a{per_page - 1}" in response.text
    assert f"f1-a{per_page}" not in response.text


def test_sync_old_entries(client):
    # TODO
    # verify that RSS_SKIP_OLDER_THAN_DAYS is honored

    # verify that if the feed doesn't have enough entries
    # RSS_MINIMUM_ENTRY_AMOUNT is honored, regardless of entry age
    pass


def test_sync_updates(client):
    feed_domain = "feed1.com"
    response, feed_id = create_feed(
        client,
        feed_domain,
        [
            {"title": "my-first-article", "date": "2023-10-01 00:00Z", "description": "initial description"},
            {"title": "my-second-article", "date": "2023-10-10 00:00Z"},
        ],
    )

    assert "my-first-article" in response.text
    assert "initial description" in response.text
    assert "my-second-article" in response.text

    mock_feed(
        feed_domain,
        [
            {"title": "my-first-article", "date": "2023-10-01 00:00Z", "description": "updated description"},
            {"title": "my-second-article", "date": "2023-10-10 00:00Z"},
            {"title": "my-third-article", "date": "2023-10-11 00:00Z"},
        ],
    )

    # force resync
    response = client.post(f"/feeds/{feed_id}/entries")
    assert response.status_code == 200

    # verify changes took effect
    response = client.get("/")
    assert "my-first-article" in response.text
    assert "updated description" in response.text
    assert "initial description" not in response.text
    assert "my-second-article" in response.text
    assert "my-third-article" in response.text


def test_sync_between_pages(client):
    # TODO verify pagination behaves reasonably if new feeds/entries
    # are added between fetching one page and the next
    pass


def test_favorites(client):
    feed_domain = "feed1.com"
    response, _feed_id = create_feed(
        client,
        feed_domain,
        [
            {"title": "my-third-article", "date": "2023-11-10 00:00Z"},
            {"title": "my-second-article", "date": "2023-10-10 00:00Z"},
            {"title": "my-first-article", "date": "2023-10-01 00:00Z"},
        ],
    )
    entry_ids = extract_entry_ids(response)

    # pin the 3rd, then the 2nd
    response = client.put(f"/favorites/{entry_ids[0]}")
    assert response.status_code == 204
    response = client.put(f"/favorites/{entry_ids[1]}")
    assert response.status_code == 204

    response = client.get("/favorites")
    assert "my-first-article" not in response.text
    assert "my-second-article" in response.text
    assert "my-third-article" in response.text

    # 2nd appears first because most recent fav, even though it's older
    assert response.text.find("my-second-article") < response.text.find("my-third-article")


def test_pinned(client):
    response, _feed_id = create_feed(
        client,
        "feed1.com",
        [{"title": "f1-a1", "date": "2023-10-01 00:00Z"}, {"title": "f1-a2", "date": "2023-10-10 00:00Z"}],
        folder="folder1",
    )
    f1a2_pin_url = re.search(r"/pinned/(\d+)", response.text).group(0)

    response, _ = create_feed(
        client,
        "feed2.com",
        [{"title": "f2-a1", "date": "2023-10-01 00:00Z"}, {"title": "f2-a2", "date": "2023-10-10 00:00Z"}],
    )
    f2_a2_pin_url = re.search(r"/pinned/(\d+)", response.text).group(0)

    response = client.get("/")
    assert "f1-a2" in response.text
    assert "f2-a2" in response.text
    response = client.get("/folder/folder1")
    assert "f1-a2" in response.text
    assert "f2-a2" not in response.text

    # add some pages of more entries in both feeds, to ensure the older ones are pushed out of the page
    now = dt.datetime.now(dt.timezone.utc)
    for i in range(1, 20):
        date = now - dt.timedelta(hours=1, minutes=1)
        create_feed(client, f"f{i}-folder1.com", [{"title": "article1", "date": date}], folder="folder1")

    # verify the old entries where pushed out of home and folder
    response = client.get("/")
    assert "f1-a2" not in response.text
    assert "f2-a2" not in response.text
    response = client.get("/folder/folder1")
    assert "f1-a2" not in response.text

    # pin the old entries
    response = client.put(f1a2_pin_url)
    assert response.status_code == 200
    response = client.put(f2_a2_pin_url)
    assert response.status_code == 200

    # verify they are pinned to the home and folder
    response = client.get("/")
    assert "f1-a2" in response.text
    assert "f2-a2" in response.text
    response = client.get("/folder/folder1")
    assert "f1-a2" in response.text
    assert "f2-a2" not in response.text


def test_entries_not_mixed_between_users(client):
    # TODO
    pass


def test_view_entry_content(client):
    # create feed with a sample entry
    with open("tests/sample.html") as sample:
        body = sample.read()
    response, _ = create_feed(
        client,
        "olano.dev",
        [
            {
                "title": "reclaiming-the-web",
                "date": "2023-12-12T00:00:00-03:00",
                "description": "short content",
                "body": body,
            }
        ],
    )
    assert "reclaiming-the-web" in response.text
    assert "short content" in response.text
    entry_url = re.search(r"/entries/(\d+)", response.text).group(0)
    response = client.get(entry_url)

    assert "reclaiming-the-web" in response.text
    assert "I had some ideas of what I wanted" in response.text


def test_add_external_entry(client):
    with open("tests/sample.html") as sample:
        body = sample.read()
    content_url = "http://olano.dev/reclaiming-the-web"
    mock_request(content_url, body=body)

    # add a standalone entry for that url, check that browser redirects to view content
    response = client.post("/entries/", query_string={"url": content_url, "redirect": 1}, follow_redirects=True)
    assert response.status_code == 200
    assert "reclaiming-the-web" in response.text
    assert "I had some ideas of what I wanted" in response.text

    # add same url again, verify that redirected entry url is the same as before
    previous_entry_url = response.request.path
    response = client.post("/entries/", query_string={"url": content_url, "redirect": 1}, follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == previous_entry_url

    # check that standalone entry appears in feed
    client.post("/session/hide_seen")
    response = client.get("/")
    assert "reclaiming-the-web" in response.text
    # short content taken from page meta description
    assert "There’s a kind of zen flow" in response.text


def test_discover_feed(client):
    # TODO
    pass


def test_feed_list(client):
    # TODO
    pass


def test_feed_edit(client):
    # TODO
    pass


def _set_kindle_email(app, email_addr):
    from feedi.models import User, db

    with app.app_context():
        user = db.session.scalar(db.select(User).order_by(User.id.desc()))
        user.kindle_email = email_addr
        db.session.commit()
        return user.id


def _make_fake_article(title):
    return {
        "title": title,
        "byline": "Test Author",
        "siteName": "Test Site",
        "content": "<p>fake body for " + title + "</p>",
        "lang": "en",
        "publishedTime": "2024-01-01",
    }


def test_queue_toggle(client, app):
    response, _feed_id = create_feed(
        client,
        "queue-feed.com",
        [
            {"title": "qa-1", "date": "2024-01-01 00:00Z"},
            {"title": "qa-2", "date": "2024-01-02 00:00Z"},
        ],
    )
    entry_ids = extract_entry_ids(response)

    # toggle on
    response = client.put(f"/queued/{entry_ids[0]}")
    assert response.status_code == 204

    response = client.get("/entries/queue")
    assert "qa-1" in response.text or "qa-2" in response.text

    # toggle off
    response = client.put(f"/queued/{entry_ids[0]}")
    assert response.status_code == 204


def test_digest_send_success(client, app, monkeypatch):
    import feedi.email
    import feedi.scraping
    import feedi.tasks
    from feedi.models import Entry, User, db

    response, _feed_id = create_feed(
        client,
        "digest-feed.com",
        [
            {"title": "da-1", "date": "2024-01-01 00:00Z"},
            {"title": "da-2", "date": "2024-01-02 00:00Z"},
        ],
    )
    entry_ids = extract_entry_ids(response)

    # Mark both queued.
    for eid in entry_ids[:2]:
        client.put(f"/queued/{eid}")

    user_id = _set_kindle_email(app, "user@kindle.com")

    extracted = []

    def fake_extract(url=None, html=None):
        extracted.append(url)
        return _make_fake_article(url or "fake")

    sent = []

    def fake_send(recipient, attach_data, filename):
        sent.append({"recipient": recipient, "filename": filename, "bytes": attach_data})

    monkeypatch.setattr(feedi.scraping, "extract", fake_extract)
    monkeypatch.setattr(feedi.email, "send", fake_send)
    # also patch the names imported into the tasks module
    monkeypatch.setattr(feedi.tasks.scraping, "extract", fake_extract)
    monkeypatch.setattr(feedi.tasks.email, "send", fake_send)

    with app.app_context():
        feedi.tasks.build_and_send_digest(user_id, "queued").get()

        user = db.session.get(User, user_id)
        status = json.loads(user.last_digest_status)
        assert status["state"] == "ok"
        assert status["sent_count"] == 2

        # queue cleared, kindle stamps set
        queued = db.session.scalars(db.select(Entry).filter(Entry.queued.is_not(None))).all()
        assert queued == []
        stamped = db.session.scalars(db.select(Entry).filter(Entry.sent_to_kindle.is_not(None))).all()
        assert len(stamped) == 2

    assert len(sent) == 1
    assert sent[0]["recipient"] == "user@kindle.com"
    assert len(extracted) == 2


def test_digest_partial_failure(client, app, monkeypatch):
    import feedi.email
    import feedi.scraping
    import feedi.tasks
    from feedi.models import Entry, User, db

    response, _feed_id = create_feed(
        client,
        "partial-feed.com",
        [
            {"title": "pa-1", "date": "2024-01-01 00:00Z"},
            {"title": "pa-2", "date": "2024-01-02 00:00Z"},
        ],
    )
    entry_ids = extract_entry_ids(response)
    for eid in entry_ids[:2]:
        client.put(f"/queued/{eid}")

    user_id = _set_kindle_email(app, "user@kindle.com")

    call_count = {"n": 0}

    def flaky_extract(url=None, html=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return _make_fake_article(url or "ok")

    sent = []

    def fake_send(recipient, attach_data, filename):
        sent.append(attach_data)

    monkeypatch.setattr(feedi.tasks.scraping, "extract", flaky_extract)
    monkeypatch.setattr(feedi.tasks.email, "send", fake_send)

    with app.app_context():
        feedi.tasks.build_and_send_digest(user_id, "queued").get()

        user = db.session.get(User, user_id)
        status = json.loads(user.last_digest_status)
        assert status["state"] == "ok"
        assert status["sent_count"] == 1
        assert len(status["failed"]) == 1

        # queue partially cleared: the failed entry stays queued.
        remaining = db.session.scalars(db.select(Entry).filter(Entry.queued.is_not(None))).all()
        assert len(remaining) == 1

    assert len(sent) == 1


def test_digest_skips_already_sent_entries(client, app, monkeypatch):
    import feedi.tasks
    from feedi.models import Entry, db

    response, _feed_id = create_feed(
        client,
        "resend-feed.com",
        [
            {"title": "re-1", "date": "2024-01-01 00:00Z"},
            {"title": "re-2", "date": "2024-01-02 00:00Z"},
        ],
    )
    entry_ids = extract_entry_ids(response)
    for eid in entry_ids[:2]:
        client.put(f"/favorites/{eid}")

    user_id = _set_kindle_email(app, "user@kindle.com")

    extracted = []

    def fake_extract(url=None, html=None):
        extracted.append(url)
        return _make_fake_article(url or "fake")

    sent = []

    def fake_send(recipient, attach_data, filename):
        sent.append(attach_data)

    monkeypatch.setattr(feedi.tasks.scraping, "extract", fake_extract)
    monkeypatch.setattr(feedi.tasks.email, "send", fake_send)

    with app.app_context():
        feedi.tasks.build_and_send_digest(user_id, "favorited").get()
        assert len(extracted) == 2

        # favorites are still favorited, but a second digest has nothing new to send
        feedi.tasks.build_and_send_digest(user_id, "favorited").get()
        assert len(extracted) == 2
        assert len(sent) == 1

    # re-favoriting after the send makes the entry eligible again
    client.put(f"/favorites/{entry_ids[0]}")  # unfavorite
    client.put(f"/favorites/{entry_ids[0]}")  # favorite again

    with app.app_context():
        feedi.tasks.build_and_send_digest(user_id, "favorited").get()
        assert len(extracted) == 3
        assert len(sent) == 2

        refavorited = db.session.get(Entry, entry_ids[0])
        assert refavorited.sent_to_kindle > refavorited.favorited


def test_digest_send_route_refuses_without_kindle_email(client):
    response = client.post("/entries/kindle/digest", data={"source": "queued"})
    assert response.status_code == 400


def test_digest_send_route_rejects_unknown_source(client, app):
    _set_kindle_email(app, "user@kindle.com")
    response = client.post("/entries/kindle/digest", data={"source": "bogus"})
    assert response.status_code == 400


def _encode_image(fmt, size=(40, 30), colour=(200, 30, 30), mode="RGB"):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, size, colour).save(buffer, format=fmt)
    return buffer.getvalue()


def test_prepare_image_converts_formats_the_kindle_cant_render():
    from feedi.scraping import _prepare_image

    # avif and webp must not reach the device declared as something they aren't
    for fmt in ("AVIF", "WEBP"):
        ext, data, media_type = _prepare_image(_encode_image(fmt), f"http://e.com/x.{fmt.lower()}")
        assert ext in ("jpg", "png"), fmt
        assert media_type in ("image/jpeg", "image/png"), fmt
        assert data[:4] not in (b"RIFF",), f"{fmt} bytes passed through unconverted"


def test_prepare_image_declares_svg_honestly():
    from feedi.scraping import _prepare_image

    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
    ext, data, media_type = _prepare_image(svg, "http://e.com/d.svg")

    # previously stored as .jpg / image/jpeg, which no reader can make sense of
    assert (ext, media_type) == ("svg", "image/svg+xml")
    assert data == svg


def test_prepare_image_downscales_to_the_panel_width():
    import io as _io

    from PIL import Image

    from feedi.scraping import MAX_IMAGE_WIDTH, _prepare_image

    wide = _encode_image("PNG", size=(MAX_IMAGE_WIDTH * 2, 400))
    _ext, data, _media_type = _prepare_image(wide, "http://e.com/wide.png")

    assert Image.open(_io.BytesIO(data)).width == MAX_IMAGE_WIDTH


def test_prepare_image_keeps_the_original_when_re_encoding_would_grow_it():
    from feedi.scraping import _prepare_image

    # a small flat-colour png is already about as small as it gets; a jpeg of it is bigger
    original = _encode_image("PNG", size=(200, 200))
    _ext, data, media_type = _prepare_image(original, "http://e.com/flat.png")

    assert len(data) <= len(original)
    assert media_type == "image/png"


def test_prepare_image_drops_undecodable_bytes():
    from feedi.scraping import _prepare_image

    assert _prepare_image(b"this is not an image at all", "http://e.com/nope.jpg") is None


def test_localize_images_leaves_unfetchable_images_pointing_at_their_source():
    from bs4 import BeautifulSoup

    from feedi.scraping import _localize_images

    soup = BeautifulSoup('<p><img src="http://e.com/gone.png"/></p>', "lxml")
    with mock.patch("feedi.scraping.safe_get", side_effect=RequestException("boom")):
        written = _localize_images(soup, "article_1_files")

    # a dangling local path would render as a broken image; the remote url at least works
    # for anything with a network connection
    assert written == []
    assert soup.find("img")["src"] == "http://e.com/gone.png"


def test_localize_images_writes_a_shared_image_once():
    from bs4 import BeautifulSoup

    from feedi.scraping import _localize_images

    png = _encode_image("PNG")
    soup = BeautifulSoup(
        '<p><img src="http://e.com/same.png"/><img src="http://e.com/same.png"/></p>',
        "lxml",
    )
    response = mock.Mock(ok=True, content=png)
    with mock.patch("feedi.scraping.safe_get", return_value=response) as fetch:
        written = _localize_images(soup, "article_1_files")

    assert fetch.call_count == 1
    assert len(written) == 1
    srcs = [img["src"] for img in soup.find_all("img")]
    assert srcs == [written[0][0], written[0][0]]


def test_package_epub_xml_safe_with_special_chars():
    from feedi.scraping import package_epub

    article = {
        "title": 'Bobby <> & "Tables"',
        "byline": "<author>",
        "siteName": "Sneaky & Co.",
        "content": "<p>fine body</p>",
        "lang": "en",
        "publishedTime": "2024-01-01",
    }
    data = package_epub("http://example.com/article", article)

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        opf = z.read("content.opf").decode()
        # If escaping is broken this will raise.
        ET.fromstring(opf)
        # The literal special chars should be escaped in the title.
        assert "Bobby <>" not in opf
        assert "Bobby &lt;&gt;" in opf


def test_package_epub_multi_article_structure():
    from feedi.scraping import package_epub

    items = [
        {"url": "http://a.example.com/1", "article": _make_fake_article("Article One")},
        {"url": "http://a.example.com/2", "article": _make_fake_article("Article Two")},
        {"url": "http://broken.example.com/3", "error": "RequestException"},
    ]
    data = package_epub(items, title="feedi digest", subtitle="Favorites")

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        assert "article_1.html" in names
        assert "article_2.html" in names
        assert "cover.xhtml" in names
        assert "nav.xhtml" in names
        assert "failures.xhtml" in names
        # No single-article file in multi-article mode.
        assert "article.html" not in names

        nav = z.read("nav.xhtml").decode()
        assert "Article One" in nav
        assert "Article Two" in nav

        failures = z.read("failures.xhtml").decode()
        assert "broken.example.com" in failures
        assert "RequestException" in failures

        # content.opf must parse as XML.
        ET.fromstring(z.read("content.opf"))


def _big_article(title, body_bytes):
    article = _make_fake_article(title)
    article["content"] = "<p>" + ("x" * body_bytes) + "</p>"
    return article


def test_package_epub_batches_splits_when_over_limit():
    from feedi.scraping import EPUB_OVERHEAD_BYTES, package_epub_batches

    # Three articles of ~40KB each against a budget that only fits one at a time.
    items = [{"url": f"http://a.example.com/{i}", "article": _big_article(f"Article {i}", 40_000)} for i in range(1, 4)]
    items.append({"url": "http://broken.example.com/x", "error": "RequestException"})

    batches = package_epub_batches(
        items, title="feedi digest", subtitle="Favorites", max_bytes=EPUB_OVERHEAD_BYTES + 60_000
    )

    assert len(batches) == 3
    assert [b["count"] for b in batches] == [1, 1, 1]
    assert [b["title"] for b in batches] == [
        "feedi digest (1/3)",
        "feedi digest (2/3)",
        "feedi digest (3/3)",
    ]

    seen_articles = []
    for number, batch in enumerate(batches, start=1):
        with zipfile.ZipFile(io.BytesIO(batch["data"])) as z:
            names = set(z.namelist())
            article_files = sorted(n for n in names if n.startswith("article_"))
            seen_articles += article_files
            assert "cover.xhtml" in names
            assert "nav.xhtml" in names
            # the TOC must link every article in this part and nothing that lives in
            # another one, otherwise the reader gets dangling links
            nav = z.read("nav.xhtml").decode()
            assert sorted(re.findall(r'href="(article_\d+\.html)"', nav)) == article_files
            # failed extractions are listed once, in the last part
            assert ("failures.xhtml" in names) == (number == len(batches))
            ET.fromstring(z.read("content.opf").decode())

    # each article appears exactly once across the batches, under a unique name
    assert sorted(seen_articles) == ["article_1.html", "article_2.html", "article_3.html"]


def test_package_epub_batches_parts_are_smaller_than_the_whole():
    from feedi.scraping import EPUB_OVERHEAD_BYTES, package_epub, package_epub_batches

    items = [{"url": f"http://a.example.com/{i}", "article": _big_article(f"Article {i}", 40_000)} for i in range(1, 4)]

    whole = package_epub(items, title="feedi digest", subtitle="Favorites")
    batches = package_epub_batches(
        items, title="feedi digest", subtitle="Favorites", max_bytes=EPUB_OVERHEAD_BYTES + 60_000
    )

    # splitting has to actually shrink each attachment, not just relabel them
    assert len(batches) == 3
    for batch in batches:
        assert len(batch["data"]) < len(whole)


def test_package_epub_batches_reports_the_items_in_each_part():
    from feedi.scraping import EPUB_OVERHEAD_BYTES, package_epub_batches

    items = [{"url": f"http://a.example.com/{i}", "article": _big_article(f"Article {i}", 40_000)} for i in range(1, 4)]
    items.append({"url": "http://broken.example.com/x", "error": "RequestException"})

    batches = package_epub_batches(
        items, title="feedi digest", subtitle="Favorites", max_bytes=EPUB_OVERHEAD_BYTES + 60_000
    )

    # the caller marks entries as sent per part, so each part must report exactly the
    # items it carried, and failed extractions must never be reported as delivered
    assert [[it["url"] for it in b["items"]] for b in batches] == [
        ["http://a.example.com/1"],
        ["http://a.example.com/2"],
        ["http://a.example.com/3"],
    ]


def test_package_epub_batches_single_batch_when_under_limit():
    from feedi.scraping import package_epub_batches

    items = [{"url": "http://a.example.com/1", "article": _make_fake_article("Article One")}]
    batches = package_epub_batches(items, title="feedi digest", subtitle="Favorites", max_bytes=16 * 1024 * 1024)

    assert len(batches) == 1
    # no "(1/1)" suffix when it all fits in one email
    assert batches[0]["title"] == "feedi digest"


def test_digest_splits_into_several_emails(client, app, monkeypatch):
    import feedi.email
    import feedi.scraping
    import feedi.tasks
    from feedi.models import User, db

    response, _feed_id = create_feed(
        client,
        "big-feed.com",
        [
            {"title": "bg-1", "date": "2024-01-01 00:00Z"},
            {"title": "bg-2", "date": "2024-01-02 00:00Z"},
        ],
    )
    entry_ids = extract_entry_ids(response)
    for eid in entry_ids[:2]:
        client.put(f"/favorites/{eid}")

    user_id = _set_kindle_email(app, "user@kindle.com")

    def fake_extract(url=None, html=None):
        return _big_article(url or "fake", 40_000)

    sent = []

    def fake_send(recipient, attach_data, filename):
        sent.append({"recipient": recipient, "filename": filename, "bytes": attach_data})

    monkeypatch.setattr(feedi.scraping, "extract", fake_extract)
    monkeypatch.setattr(feedi.email, "send", fake_send)
    monkeypatch.setattr(feedi.tasks.scraping, "extract", fake_extract)
    monkeypatch.setattr(feedi.tasks.email, "send", fake_send)
    # the app fixture is session-scoped and feedi.tasks.app is a second app built by
    # create_huey_app(), so both need setting and both need restoring
    max_bytes = feedi.scraping.EPUB_OVERHEAD_BYTES + 60_000
    monkeypatch.setitem(app.config, "MAX_ATTACHMENT_BYTES", max_bytes)
    monkeypatch.setitem(feedi.tasks.app.config, "MAX_ATTACHMENT_BYTES", max_bytes)

    with app.app_context():
        feedi.tasks.build_and_send_digest(user_id, "favorited").get()

        status = json.loads(db.session.get(User, user_id).last_digest_status)
        assert status["state"] == "ok"
        assert status["sent_count"] == 2
        assert status["parts"] == 2

    assert len(sent) == 2
    assert sent[0]["filename"].endswith("(1/2)")
    assert sent[1]["filename"].endswith("(2/2)")
    assert [s["recipient"] for s in sent] == ["user@kindle.com", "user@kindle.com"]
    # each part carries one article, so neither can be the whole digest
    assert all(len(s["bytes"]) < sum(len(o["bytes"]) for o in sent) for s in sent)


def test_digest_partial_send_keeps_delivered_articles_marked(client, app, monkeypatch):
    import feedi.email
    import feedi.scraping
    import feedi.tasks
    from feedi.models import Entry, User, db

    response, _feed_id = create_feed(
        client,
        "flaky-feed.com",
        [
            {"title": "fl-1", "date": "2024-01-01 00:00Z"},
            {"title": "fl-2", "date": "2024-01-02 00:00Z"},
        ],
    )
    entry_ids = extract_entry_ids(response)
    for eid in entry_ids[:2]:
        client.put(f"/queued/{eid}")

    user_id = _set_kindle_email(app, "user@kindle.com")

    def fake_extract(url=None, html=None):
        return _big_article(url or "fake", 40_000)

    sent = []

    def flaky_send(recipient, attach_data, filename):
        "Deliver the first part, then blow up like a dropped SMTP connection."
        if sent:
            raise OSError("connection reset")
        sent.append(filename)

    monkeypatch.setattr(feedi.scraping, "extract", fake_extract)
    monkeypatch.setattr(feedi.tasks.scraping, "extract", fake_extract)
    monkeypatch.setattr(feedi.email, "send", flaky_send)
    monkeypatch.setattr(feedi.tasks.email, "send", flaky_send)
    max_bytes = feedi.scraping.EPUB_OVERHEAD_BYTES + 60_000
    monkeypatch.setitem(app.config, "MAX_ATTACHMENT_BYTES", max_bytes)
    monkeypatch.setitem(feedi.tasks.app.config, "MAX_ATTACHMENT_BYTES", max_bytes)

    with app.app_context():
        feedi.tasks.build_and_send_digest(user_id, "queued").get()

        status = json.loads(db.session.get(User, user_id).last_digest_status)
        assert status["state"] == "failed"
        # the part that did go out is reported, not silently counted as nothing
        assert status["sent_count"] == 1
        assert status["parts"] == 1

        # exactly the delivered article stays marked, so a retry sends only the other one
        stamped = db.session.scalars(
            db.select(Entry).filter(Entry.id.in_(entry_ids), Entry.sent_to_kindle.is_not(None))
        ).all()
        assert len(stamped) == 1
        assert stamped[0].queued is None
        assert stamped[0].viewed is not None

        retry = Entry.select_for_digest(user_id, "queued")
        assert len(retry) == 1
        assert retry[0].id != stamped[0].id

    assert len(sent) == 1


def test_safe_get_rejects_loopback(app):
    from feedi.requests import UnsafeURLError, safe_get

    # Disable the testing bypass for this single call.
    with app.app_context():
        app.config["DISABLE_SSRF_GUARD"] = False
        try:
            try:
                safe_get("http://127.0.0.1/admin")
                assert False, "expected UnsafeURLError"
            except UnsafeURLError:
                pass

            try:
                safe_get("file:///etc/passwd")
                assert False, "expected UnsafeURLError"
            except UnsafeURLError:
                pass
        finally:
            app.config["DISABLE_SSRF_GUARD"] = True


def test_feed_delete(client):
    response, feed_id = create_feed(
        client,
        "feed1.com",
        [
            {"title": "pin-entry", "date": "2023-12-01 00:00Z"},
            {"title": "fav-entry", "date": "2023-11-10 00:00Z"},
            {"title": "plain-entry", "date": "2023-10-10 00:00Z"},
        ],
    )

    response = client.get("/")
    assert "pin-entry" in response.text
    assert "fav-entry" in response.text
    assert "plain-entry" in response.text

    # check the 3 appear when requesting by feed name
    response = client.get(f"/feeds/{feed_id}/entries")
    assert "pin-entry" in response.text
    assert "fav-entry" in response.text
    assert "plain-entry" in response.text

    # pin the 1st, fav the 2nd
    entry_ids = extract_entry_ids(response)
    response = client.put("/pinned/" + entry_ids[0])
    assert response.status_code == 200

    response = client.put("/favorites/" + entry_ids[1])
    assert response.status_code == 204

    # delete the feed
    response = client.delete(f"/feeds/{feed_id}")
    assert response.status_code == 204

    # check pinned and favorited appear on home, the other is deleted
    response = client.get("/")
    assert "pin-entry" in response.text
    assert "fav-entry" in response.text
    assert "plain-entry" not in response.text

    # check empty when requesting by feed name
    response = client.get(f"/feeds/{feed_id}/entries")
    assert "pin-entry" not in response.text
    assert "fav-entry" not in response.text
    assert "plain-entry" not in response.text
