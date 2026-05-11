"""
JSON API for feedi, used by the Kindle-friendly web client.

Auth is via the existing Flask-Login session cookie. An ``@api_login_required``
decorator returns JSON 401 instead of redirecting to the HTML login view.
"""

import datetime
import functools

import flask
import sqlalchemy as sa
from flask import current_app
from flask_login import current_user

import feedi.email as email
import feedi.models as models
from feedi import scraping
from feedi.models import db

api = flask.Blueprint("api", __name__, url_prefix="/api/v1")


def api_login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return flask.jsonify({"error": "unauthenticated"}), 401
        return view(*args, **kwargs)

    return wrapper


def _iso(value):
    return value.isoformat() if value else None


def serialize_user(user):
    return {
        "id": user.id,
        "email": user.email,
        "has_kindle": bool(user.kindle_email),
    }


def serialize_feed(feed):
    return {
        "id": feed.id,
        "name": feed.name,
        "type": feed.type,
        "url": feed.url,
        "icon_url": feed.icon_url,
        "folder": feed.folder,
    }


def serialize_entry(entry, include_content=False):
    data = {
        "id": entry.id,
        "title": entry.title,
        "header": entry.header,
        "username": entry.username,
        "display_name": entry.display_name,
        "avatar_url": entry.avatar_url,
        "icon_url": entry.icon_url,
        "content_short": entry.content_short,
        "target_url": entry.target_url,
        "content_url": entry.content_url,
        "comments_url": entry.comments_url,
        "media_url": entry.media_url,
        "display_date": _iso(entry.display_date),
        "sort_date": _iso(entry.sort_date),
        "viewed": _iso(entry.viewed),
        "favorited": _iso(entry.favorited),
        "pinned": _iso(entry.pinned),
        "sent_to_kindle": _iso(entry.sent_to_kindle),
        "feed": serialize_feed(entry.feed) if entry.feed else None,
    }
    if include_content:
        data["content_full"] = entry.content_full
    return data


def _get_user_entry(id, undefer_content=False):
    options = [sa.orm.undefer(models.Entry.content_full)] if undefer_content else []
    entry = db.get_or_404(models.Entry, id, options=options or None)
    if entry.user_id != current_user.id:
        flask.abort(404)
    return entry


def _parse_entry_filters(args):
    out = {}
    for key in ("feed_id", "folder", "username"):
        value = args.get(key)
        if value:
            out[key] = value
    if args.get("favorited"):
        out["favorited"] = True
    if args.get("sent_to_kindle"):
        out["sent_to_kindle"] = True
    text = args.get("q", "").strip()
    if text:
        out["text"] = text
    return out


@api.get("/me")
@api_login_required
def me():
    return flask.jsonify(serialize_user(current_user))


@api.get("/feeds")
@api_login_required
def feed_list():
    feeds = db.session.scalars(
        db.select(models.Feed).filter_by(user_id=current_user.id).order_by(models.Feed.name)
    ).all()
    return flask.jsonify({"feeds": [serialize_feed(f) for f in feeds]})


@api.get("/folders")
@api_login_required
def folder_list():
    folders = db.session.scalars(
        db.select(models.Feed.folder)
        .filter(models.Feed.folder.isnot(None), models.Feed.folder != "")
        .filter_by(user_id=current_user.id)
        .distinct()
        .order_by(models.Feed.folder)
    ).all()
    return flask.jsonify({"folders": list(folders)})


@api.get("/entries")
@api_login_required
def entry_list():
    args = flask.request.args
    filters = _parse_entry_filters(args)

    cursor = args.get("cursor")
    if cursor:
        try:
            ts_str, page_str = cursor.split(":")
            start_at = datetime.datetime.fromtimestamp(float(ts_str))
            page_num = int(page_str)
        except (ValueError, TypeError):
            return flask.jsonify({"error": "invalid cursor"}), 400
    else:
        start_at = datetime.datetime.utcnow()
        page_num = 1

    is_mixed_feed_list = not any(filters.get(k) for k in ("feed_id", "username", "favorited", "sent_to_kindle"))

    hide_seen_param = args.get("hide_seen")
    if hide_seen_param is not None:
        filters["hide_seen"] = hide_seen_param.lower() in ("1", "true", "yes")
    else:
        filters["hide_seen"] = is_mixed_feed_list

    if is_mixed_feed_list and not args.get("include_old"):
        filters["newer_than"] = datetime.datetime.utcnow() - datetime.timedelta(days=14)

    query = models.Entry.filter_by(current_user.id, start_at, **filters).options(sa.orm.selectinload(models.Entry.feed))
    page = db.paginate(query, per_page=current_app.config["ENTRY_PAGE_SIZE"], page=page_num)
    next_cursor = f"{start_at.timestamp()}:{page_num + 1}" if page.has_next else None

    # Mirror routes.fetch_entries_page: when paginating past the first page,
    # mark the previous page as viewed.
    if page.has_prev:
        previous_ids = [e.id for e in page.prev().items]
        if previous_ids:
            db.session.execute(
                db.update(models.Entry)
                .where(models.Entry.id.in_(previous_ids))
                .values(viewed=datetime.datetime.utcnow())
            )
            db.session.commit()

    return flask.jsonify(
        {
            "entries": [serialize_entry(e) for e in page.items],
            "next_cursor": next_cursor,
        }
    )


@api.get("/entries/pinned")
@api_login_required
def entry_pinned_list():
    filters = _parse_entry_filters(flask.request.args)
    pinned = models.Entry.select_pinned(current_user.id, **filters)
    return flask.jsonify({"entries": [serialize_entry(e) for e in pinned]})


@api.get("/entries/<int:id>")
@api_login_required
def entry_detail(id):
    entry = _get_user_entry(id)
    return flask.jsonify(serialize_entry(entry))


@api.get("/entries/<int:id>/content")
@api_login_required
def entry_content(id):
    entry = _get_user_entry(id, undefer_content=True)

    if not entry.content_url and not entry.target_url:
        return flask.jsonify({"error": "entry not readable"}), 400

    # Clients can pass ?prefetch=1 to warm content in the DB without
    # marking the entry as viewed (used for next-in-list pre-fetch).
    is_prefetch = flask.request.args.get("prefetch", "").lower() in ("1", "true", "yes")

    if entry.content_url:
        entry.fetch_content()

    if entry.content_full:
        if not is_prefetch:
            entry.viewed = entry.viewed or datetime.datetime.utcnow()
        db.session.commit()
        return flask.jsonify(serialize_entry(entry, include_content=True))

    # No local content available — caller should open target_url externally.
    return flask.jsonify(
        {
            "id": entry.id,
            "content_full": None,
            "target_url": entry.target_url,
            "external_only": True,
        }
    )


@api.put("/entries/<int:id>/pin")
@api_login_required
def entry_pin(id):
    entry = _get_user_entry(id)
    if not entry.pinned:
        entry.fetch_content()
        entry.pinned = datetime.datetime.utcnow()
        db.session.commit()
    return flask.jsonify(serialize_entry(entry))


@api.delete("/entries/<int:id>/pin")
@api_login_required
def entry_unpin(id):
    entry = _get_user_entry(id)
    entry.pinned = None
    db.session.commit()
    return "", 204


@api.put("/entries/<int:id>/favorite")
@api_login_required
def entry_favorite(id):
    entry = _get_user_entry(id)
    if not entry.favorited:
        entry.favorited = datetime.datetime.utcnow()
        db.session.commit()
    return flask.jsonify(serialize_entry(entry))


@api.delete("/entries/<int:id>/favorite")
@api_login_required
def entry_unfavorite(id):
    entry = _get_user_entry(id)
    entry.favorited = None
    db.session.commit()
    return "", 204


@api.post("/entries/<int:id>/viewed")
@api_login_required
def entry_mark_viewed(id):
    entry = _get_user_entry(id)
    entry.viewed = entry.viewed or datetime.datetime.utcnow()
    db.session.commit()
    return "", 204


@api.post("/entries/<int:id>/kindle")
@api_login_required
def entry_send_to_kindle(id):
    if not current_user.kindle_email:
        return flask.jsonify({"error": "no kindle email configured"}), 400

    entry = _get_user_entry(id)
    url = entry.content_url or entry.target_url
    if not url:
        return flask.jsonify({"error": "entry has no url"}), 400

    article = scraping.extract(url)
    attach_data = scraping.package_epub(url, article)
    email.send(current_user.kindle_email, attach_data, filename=article["title"])

    entry.sent_to_kindle = datetime.datetime.utcnow()
    entry.viewed = entry.viewed or datetime.datetime.utcnow()
    entry.content_full = article["content"]
    db.session.commit()

    return flask.jsonify(serialize_entry(entry))


@api.post("/entries")
@api_login_required
def entry_create():
    data = flask.request.get_json(silent=True) or {}
    url = data.get("url") or flask.request.args.get("url")
    if not url:
        return flask.jsonify({"error": "url is required"}), 400

    try:
        entry = models.Entry.from_url(current_user.id, url)
    except Exception:
        return flask.jsonify({"error": "failed to parse entry"}), 500

    db.session.add(entry)
    db.session.commit()
    return flask.jsonify(serialize_entry(entry)), 201
