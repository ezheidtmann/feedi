import datetime as dt
import re

from tests.conftest import create_feed


def _entry_id_from_response(response):
    return int(re.search(r"/entries/(\d+)", response.text).group(1))


def test_api_requires_auth(app):
    client = app.test_client()
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.get_json()["error"]


def test_api_me(client):
    resp = client.get("/api/v1/me")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "@" in data["email"]
    assert isinstance(data["id"], int)
    assert data["has_kindle"] is False


def test_api_entries_list(client):
    create_feed(
        client,
        "api-feed1.com",
        [
            {"title": "api-first-article", "date": "2023-10-01 00:00Z"},
            {"title": "api-second-article", "date": "2023-10-10 00:00Z"},
        ],
    )
    resp = client.get("/api/v1/entries")
    assert resp.status_code == 200
    data = resp.get_json()
    titles = [e["title"] for e in data["entries"]]
    assert "api-first-article" in titles
    assert "api-second-article" in titles
    # newest first
    assert titles.index("api-second-article") < titles.index("api-first-article")
    assert all(e["feed"]["name"] == "api-feed1.com" for e in data["entries"])


def test_api_entries_filter_by_feed(client):
    _, feed1_id = create_feed(client, "api-fbf1.com", [{"title": "fbf1-a1", "date": "2023-10-01 00:00Z"}])
    create_feed(client, "api-fbf2.com", [{"title": "fbf2-a1", "date": "2023-10-02 00:00Z"}])

    resp = client.get(f"/api/v1/entries?feed_id={feed1_id}")
    titles = [e["title"] for e in resp.get_json()["entries"]]
    assert "fbf1-a1" in titles
    assert "fbf2-a1" not in titles


def test_api_folder_filter_and_listing(client):
    create_feed(client, "api-fld1.com", [{"title": "fld-news-a1", "date": "2023-10-01 00:00Z"}], folder="news")
    create_feed(client, "api-fld2.com", [{"title": "fld-tech-a1", "date": "2023-10-02 00:00Z"}], folder="tech")

    resp = client.get("/api/v1/entries?folder=news")
    titles = [e["title"] for e in resp.get_json()["entries"]]
    assert "fld-news-a1" in titles
    assert "fld-tech-a1" not in titles

    resp = client.get("/api/v1/folders")
    folders = resp.get_json()["folders"]
    assert sorted(folders) == ["news", "tech"]


def test_api_feeds_listing(client):
    create_feed(client, "api-fl1.com", [{"title": "fl-a1", "date": "2023-10-01 00:00Z"}])
    create_feed(client, "api-fl2.com", [{"title": "fl-a2", "date": "2023-10-02 00:00Z"}])

    resp = client.get("/api/v1/feeds")
    names = sorted(f["name"] for f in resp.get_json()["feeds"])
    assert names == ["api-fl1.com", "api-fl2.com"]


def test_api_favorite_lifecycle(client):
    response, _ = create_feed(client, "api-fav.com", [{"title": "fav-article", "date": "2023-10-01 00:00Z"}])
    entry_id = _entry_id_from_response(response)

    resp = client.get("/api/v1/entries?favorited=1")
    assert resp.get_json()["entries"] == []

    resp = client.put(f"/api/v1/entries/{entry_id}/favorite")
    assert resp.status_code == 200
    assert resp.get_json()["favorited"] is not None

    resp = client.get("/api/v1/entries?favorited=1")
    titles = [e["title"] for e in resp.get_json()["entries"]]
    assert "fav-article" in titles

    resp = client.delete(f"/api/v1/entries/{entry_id}/favorite")
    assert resp.status_code == 204

    resp = client.get("/api/v1/entries?favorited=1")
    assert resp.get_json()["entries"] == []


def test_api_pin_lifecycle(client):
    response, _ = create_feed(client, "api-pin.com", [{"title": "pin-article", "date": "2023-10-01 00:00Z"}])
    entry_id = _entry_id_from_response(response)

    resp = client.get("/api/v1/entries/pinned")
    assert resp.get_json()["entries"] == []

    resp = client.put(f"/api/v1/entries/{entry_id}/pin")
    assert resp.status_code == 200
    assert resp.get_json()["pinned"] is not None

    resp = client.get("/api/v1/entries/pinned")
    titles = [e["title"] for e in resp.get_json()["entries"]]
    assert "pin-article" in titles

    resp = client.delete(f"/api/v1/entries/{entry_id}/pin")
    assert resp.status_code == 204
    resp = client.get("/api/v1/entries/pinned")
    assert resp.get_json()["entries"] == []


def test_api_mark_viewed(client):
    response, _ = create_feed(client, "api-view.com", [{"title": "view-article", "date": "2023-10-01 00:00Z"}])
    entry_id = _entry_id_from_response(response)

    resp = client.get(f"/api/v1/entries/{entry_id}")
    assert resp.get_json()["viewed"] is None

    resp = client.post(f"/api/v1/entries/{entry_id}/viewed")
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/entries/{entry_id}")
    assert resp.get_json()["viewed"] is not None


def test_api_search(client):
    create_feed(
        client,
        "api-search.com",
        [
            {"title": "python-tips-api", "date": "2023-10-01 00:00Z"},
            {"title": "javascript-tricks-api", "date": "2023-10-02 00:00Z"},
        ],
    )

    resp = client.get("/api/v1/entries?q=python-tips-api")
    titles = [e["title"] for e in resp.get_json()["entries"]]
    assert "python-tips-api" in titles
    assert "javascript-tricks-api" not in titles


def test_api_pagination(client):
    # use recent dates so the RSS parser keeps all entries (RSS_SKIP_OLDER_THAN_DAYS=30)
    base = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    items = [{"title": f"pg-art-{i:02d}", "date": (base - dt.timedelta(hours=i)).isoformat()} for i in range(1, 16)]
    _, feed_id = create_feed(client, "api-pg.com", items)

    # filter to this feed so we know the page set, and disable hide_seen so re-pagination
    # in the same session is stable
    resp = client.get(f"/api/v1/entries?feed_id={feed_id}&hide_seen=false")
    data = resp.get_json()
    assert len(data["entries"]) == 10
    assert data["next_cursor"] is not None

    resp = client.get(f"/api/v1/entries?feed_id={feed_id}&hide_seen=false&cursor={data['next_cursor']}")
    data2 = resp.get_json()
    assert len(data2["entries"]) >= 1
    first_ids = {e["id"] for e in data["entries"]}
    second_ids = {e["id"] for e in data2["entries"]}
    assert first_ids.isdisjoint(second_ids)


def test_api_invalid_cursor(client):
    resp = client.get("/api/v1/entries?cursor=not-a-cursor")
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_api_entry_detail_404(client):
    resp = client.get("/api/v1/entries/9999999")
    assert resp.status_code == 404


def test_api_kindle_without_email_set(client):
    response, _ = create_feed(client, "api-kndl.com", [{"title": "kndl-article", "date": "2023-10-01 00:00Z"}])
    entry_id = _entry_id_from_response(response)

    resp = client.post(f"/api/v1/entries/{entry_id}/kindle")
    assert resp.status_code == 400
    assert "kindle" in resp.get_json()["error"].lower()
