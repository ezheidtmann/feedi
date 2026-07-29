import hashlib
import io
import json
import logging
import subprocess
import urllib
import zipfile
from xml.sax.saxutils import escape as xml_escape
from xml.sax.saxutils import quoteattr

import dateparser

# use internal module to access unexported .tags function
import favicon.favicon as favicon
from bs4 import BeautifulSoup
from PIL import Image
from requests.exceptions import RequestException

from feedi.requests import TIMEOUT_SLOWER, USER_AGENT, requests, safe_get

logger = logging.getLogger(__name__)


def get_favicon(url, html=None):
    "Return the best favicon from the given url, or None."
    url_parts = urllib.parse.urlparse(url)
    url = f"{url_parts.scheme}://{url_parts.netloc}"

    try:
        if not html:
            favicons = favicon.get(url, headers={"User-Agent": USER_AGENT}, timeout=2)
        else:
            favicons = sorted(favicon.tags(url, html), key=lambda i: i.width + i.height, reverse=True)
    except Exception:
        logger.exception("error fetching favicon: %s", url)
        return

    # if there's an .ico one, prefer it since it's more likely to be
    # a square icon rather than a banner
    ico_format = [f for f in favicons if f.format == "ico"]
    if ico_format:
        return ico_format[0].url

    # otherwise return the first
    return favicons[0].url if favicons else None


class CachingRequestsMixin:
    """
    Exposes a request method that caches the response contents for subsequent requests.
    """

    def __init__(self):
        self.response_cache = {}

    # TODO make this a proper cache of any sort of request, and cache all.
    def request(self, url):
        """
        GET the content of the given url, and if the response is successful
        cache it for subsequent calls to this method.
        """
        if url in self.response_cache:
            logger.debug("using cached response %s", url)
            return self.response_cache[url]

        logger.debug("making request %s", url)
        content = requests.get(url).content
        self.response_cache[url] = content
        return content

    def fetch_meta(self, url, *tags):
        """
        GET the body of the url (which could be already cached) and extract the content of the given meta tag.
        """
        soup = BeautifulSoup(self.request(url), "lxml")
        return extract_meta(soup, *tags)


def extract_meta(soup, *tags):
    for tag in tags:
        for attr in ["property", "name", "itemprop"]:
            meta_tag = soup.find("meta", {attr: tag}, content=True)
            if meta_tag:
                return meta_tag["content"]


def all_meta(soup):
    result = {}
    for attr in ["property", "name", "itemprop"]:
        for meta_tag in soup.find_all("meta", {attr: True}, content=True):
            result[meta_tag[attr]] = meta_tag["content"]
    return result


def make_absolute(url, path):
    "If `path` is a relative url, join it with the given absolute url."
    if not urllib.parse.urlparse(path).netloc:
        path = urllib.parse.urljoin(url, path)
    return path


# TODO this should be renamed, and maybe other things in this modules, using extract too much
def extract(url=None, html=None):
    # The mozilla/readability npm package shows better results at extracting the
    # article content than all the python libraries I've tried... even than the readabilipy
    # one, which is a wrapper of it. so resorting to running a node.js script on a subprocess
    # for parsing the article sadly this adds a dependency to node and a few npm pacakges
    if url:
        html = safe_get(url, timeout=TIMEOUT_SLOWER).content
    elif not html:
        raise ValueError("Expected either url or html")

    r = subprocess.run(["feedi/extract_article.js", "--stdin", url], input=html, capture_output=True, check=True)

    article = json.loads(r.stdout)

    # load lazy images by replacing putting the data-src into src and stripping other attrs
    soup = BeautifulSoup(article["content"], "lxml")

    LAZY_DATA_ATTRS = ["data-src", "data-lazy-src", "data-td-src-property", "data-srcset"]
    for data_attr in LAZY_DATA_ATTRS:
        for img in soup.findAll("img", attrs={data_attr: True}):
            img.attrs = {"src": img[data_attr]}

    # prevent video iframes to force dimensions
    for iframe in soup.findAll("iframe", height=True):
        del iframe["height"]

    article["content"] = str(soup)

    return article


CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def _resolve_author(url, article):
    author = article.get("byline") or article.get("siteName")
    if not author:
        author = urllib.parse.urlparse(url).netloc.replace("www.", "")
    return author


def _resolve_published(article):
    published = article.get("publishedTime") or ""
    published = published and dateparser.parse(published)
    return published and published.date().isoformat()


def _localize_images(soup, subdir):
    """
    Walk every <img>, fetch it and rewrite the src to a local path under `subdir/`.
    Returns the list of (filename, data, media-type) to write into the epub zip.
    Filenames are hashed to avoid collisions when two source URLs share a basename.
    """
    written = []
    seen = set()
    for img in soup.findAll("img"):
        img_url = img.get("src")
        if not img_url:
            continue

        digest = hashlib.sha1(img_url.encode("utf-8")).hexdigest()[:10]
        ext = img_url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
            ext = "jpg"
        is_webp = ext == "webp"
        if is_webp:
            ext = "jpg"
        img_filename = f"{subdir}/{digest}.{ext}"

        img["src"] = img_filename

        if img_filename in seen:
            continue
        seen.add(img_filename)

        try:
            response = safe_get(img_url, timeout=TIMEOUT_SLOWER)
            if not response.ok:
                continue
        except (RequestException, ValueError):
            logger.exception("error fetching image during epub generation: %s", img_url)
            continue

        try:
            if is_webp:
                buffer = io.BytesIO()
                Image.open(io.BytesIO(response.content)).convert("RGB").save(buffer, "JPEG")
                data = buffer.getvalue()
            else:
                data = response.content
        except Exception:
            logger.exception("error converting image for epub: %s", img_url)
            continue

        media_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        written.append((img_filename, data, media_type))
    return written


def _article_header_html(article, url):
    title = xml_escape(article.get("title") or url or "Untitled")
    parts = [f"<h1>{title}</h1>"]
    byline = article.get("byline") or article.get("siteName")
    if byline:
        parts.append(f"<p><em>{xml_escape(byline)}</em></p>")
    published = _resolve_published(article)
    if published:
        parts.append(f"<p><small>{xml_escape(published)}</small></p>")
    if url:
        parts.append(f"<p><small><a href={quoteattr(url)}>{xml_escape(url)}</a></small></p>")
    parts.append("<hr/>")
    return "".join(parts)


# Local header + central directory entry + the manifest line the file needs in the opf.
# Measured at ~137 bytes; rounded up so the batch estimate stays an upper bound.
ZIP_ENTRY_OVERHEAD_BYTES = 256


def _split_items(items):
    "Partition digest items into the ones that extracted cleanly and the ones that didn't."
    successes = [it for it in items if "article" in it and it.get("article")]
    failures = [it for it in items if "article" not in it or not it.get("article")]
    return successes, failures


def _render_article(item, idx, single=False):
    """
    Render one extracted item into the xhtml document and image blobs that represent it
    inside an epub. Images are fetched here, so rendering an article once is enough even
    when the digest ends up split across several epubs.
    """
    art = item["article"]
    item_url = item.get("url") or ""
    header = "" if single else _article_header_html(art, item_url)
    soup = BeautifulSoup(art.get("content") or "", "lxml")
    images = _localize_images(soup, f"article_{idx}_files")
    title_for_doc = xml_escape(art.get("title") or item_url or "Untitled")
    html = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        f"<head><title>{title_for_doc}</title></head>\n"
        f"<body>{header}{str(soup)}</body>\n"
        "</html>"
    )
    return {
        "idx": idx,
        "item": item,
        "href": "article.html" if single else f"article_{idx}.html",
        "html": html,
        "images": images,
        # What this article costs the zip: its uncompressed payload (images are already
        # compressed, so deflate wins nothing back on them) plus the per-file zip and
        # manifest overhead, which grows with the file count rather than the byte count.
        "size": (
            len(html.encode("utf-8"))
            + sum(len(data) for _, data, _ in images)
            + ZIP_ENTRY_OVERHEAD_BYTES * (1 + len(images))
        ),
    }


def _zip_epub(rendered, failures, *, title=None, subtitle=None, single=False):
    "Assemble already-rendered articles into the bytes of one epub file."
    output_buffer = io.BytesIO()
    with zipfile.ZipFile(output_buffer, "w") as zip:
        # mimetype must be first and uncompressed per https://www.w3.org/TR/epub-33/#sec-zip-container-mime
        zip.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zip.writestr("META-INF/container.xml", CONTAINER_XML, compress_type=zipfile.ZIP_DEFLATED)

        manifest_items = []
        spine_items = []
        image_manifest = []

        # Cover and TOC nav only make sense for digests.
        if not single:
            cover_html = _build_cover_html(title or "feedi digest", subtitle, len(rendered))
            zip.writestr("cover.xhtml", cover_html, compress_type=zipfile.ZIP_DEFLATED)
            manifest_items.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
            spine_items.append('<itemref idref="cover"/>')

        for doc in rendered:
            idx = doc["idx"]
            for img_filename, data, media_type in doc["images"]:
                zip.writestr(img_filename, data, compress_type=zipfile.ZIP_DEFLATED)
                image_manifest.append((img_filename, media_type))

            zip.writestr(doc["href"], doc["html"], compress_type=zipfile.ZIP_DEFLATED)
            manifest_items.append(f'<item id="article{idx}" href="{doc["href"]}" media-type="application/xhtml+xml"/>')
            spine_items.append(f'<itemref idref="article{idx}"/>')

        if failures:
            failures_html = _build_failures_html(failures)
            zip.writestr("failures.xhtml", failures_html, compress_type=zipfile.ZIP_DEFLATED)
            manifest_items.append('<item id="failures" href="failures.xhtml" media-type="application/xhtml+xml"/>')
            spine_items.append('<itemref idref="failures"/>')

        for img_path, media_type in image_manifest:
            safe_id = "img_" + hashlib.sha1(img_path.encode()).hexdigest()[:10]
            manifest_items.append(f'<item id="{safe_id}" href="{xml_escape(img_path)}" media-type="{media_type}"/>')

        if single:
            first = rendered[0]["item"]
            doc_title = first["article"].get("title") or first.get("url") or "Untitled"
            doc_author = _resolve_author(first.get("url") or "", first["article"])
            doc_lang = first["article"].get("lang") or ""
            doc_date = _resolve_published(first["article"]) or ""
        else:
            doc_title = title or "feedi digest"
            doc_author = "feedi"
            doc_lang = "en"
            doc_date = ""
            nav_html = _build_nav_html(doc_title, rendered)
            zip.writestr("nav.xhtml", nav_html, compress_type=zipfile.ZIP_DEFLATED)
            manifest_items.append(
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            )

        opf = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" xml:lang="en" '
            'unique-identifier="uid" prefix="cc: http://creativecommons.org/ns#">\n'
            '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'    <dc:identifier id="uid">feedi-{hashlib.sha1(doc_title.encode()).hexdigest()[:12]}</dc:identifier>\n'
            f'    <dc:title id="title">{xml_escape(doc_title)}</dc:title>\n'
            f"    <dc:creator>{xml_escape(doc_author)}</dc:creator>\n"
            f"    <dc:language>{xml_escape(doc_lang)}</dc:language>\n"
            f"    <dc:date>{xml_escape(doc_date)}</dc:date>\n"
            "  </metadata>\n"
            "  <manifest>\n    " + "\n    ".join(manifest_items) + "\n  </manifest>\n"
            "  <spine>\n    " + "\n    ".join(spine_items) + "\n  </spine>\n"
            "</package>"
        )
        zip.writestr("content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)

    return output_buffer.getvalue()


def package_epub(url_or_items, article=None, *, title=None, subtitle=None):
    """
    Build an EPUB containing one or more articles, returning the zipped bytes.

    Backwards-compatible single-article call: `package_epub(url, article)`.
    Digest call: `package_epub(items, title=..., subtitle=...)` where each item is
        {"url": str, "article": readability-dict} for successes and
        {"url": str, "error": str} for failed items (rendered as a final chapter).
    """
    if isinstance(url_or_items, str):
        items = [{"url": url_or_items, "article": article}]
        single = True
    else:
        items = list(url_or_items)
        single = False

    successes, failures = _split_items(items)
    if not successes:
        raise ValueError("package_epub needs at least one successfully extracted article")

    rendered = [_render_article(it, idx, single=single) for idx, it in enumerate(successes, start=1)]
    return _zip_epub(rendered, failures, title=title, subtitle=subtitle, single=single)


# Room left for the epub container files (cover, nav, opf) on top of the article
# payload when deciding where to cut a batch.
EPUB_OVERHEAD_BYTES = 32 * 1024


def package_epub_batches(items, *, title=None, subtitle=None, max_bytes):
    """
    Package a digest into as many epubs as it takes to keep each one under `max_bytes`,
    so an oversized digest can go out as several emails instead of being rejected by the
    mail server. Returns a list of {"data", "title", "count", "items"} dicts, in reading
    order; "items" are the input items that went into that epub.

    Articles (and their images) are fetched and rendered exactly once, then assembled
    into batches, so splitting costs no extra network traffic. Failed extractions are
    listed in the last batch.
    """
    items = list(items)
    successes, failures = _split_items(items)
    if not successes:
        raise ValueError("package_epub_batches needs at least one successfully extracted article")

    rendered = [_render_article(it, idx) for idx, it in enumerate(successes, start=1)]

    # Greedy pack on the uncompressed estimate from _render_article, which bounds the
    # zipped result from above, less a reserve for the cover/nav/opf that every epub
    # carries regardless of how many articles are in it.
    budget = max(max_bytes - EPUB_OVERHEAD_BYTES, 1)
    batches = []
    current = []
    current_size = 0
    for doc in rendered:
        if current and current_size + doc["size"] > budget:
            batches.append(current)
            current, current_size = [], 0
        if not current and doc["size"] > budget:
            # nothing to split further: it goes out alone and may still be rejected
            logger.warning(
                "digest: article %s needs %d bytes on its own, over the %d byte budget",
                doc["item"].get("url"),
                doc["size"],
                budget,
            )
        current.append(doc)
        current_size += doc["size"]
    batches.append(current)

    total = len(batches)
    packaged = []
    for number, batch in enumerate(batches, start=1):
        base_title = title or "feedi digest"
        batch_title = base_title if total == 1 else f"{base_title} ({number}/{total})"
        data = _zip_epub(
            batch,
            failures if number == total else [],
            title=batch_title,
            subtitle=subtitle,
        )
        packaged.append(
            {
                "data": data,
                "title": batch_title,
                "count": len(batch),
                "items": [doc["item"] for doc in batch],
            }
        )

    return packaged


def _build_cover_html(title, subtitle, count):
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE html>",
        '<html xmlns="http://www.w3.org/1999/xhtml">',
        f"<head><title>{xml_escape(title)}</title></head>",
        '<body style="text-align:center;">',
        f"<h1>{xml_escape(title)}</h1>",
    ]
    if subtitle:
        parts.append(f"<h2>{xml_escape(subtitle)}</h2>")
    parts.append(f"<p>{count} article{'s' if count != 1 else ''}</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _build_nav_html(title, rendered):
    lis = []
    for doc in rendered:
        item = doc["item"]
        art_title = item["article"].get("title") or item.get("url") or f"Article {doc['idx']}"
        lis.append(f'<li><a href="{doc["href"]}">{xml_escape(art_title)}</a></li>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f"<head><title>{xml_escape(title)}</title></head>\n"
        "<body>\n"
        '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + "".join(lis) + "</ol></nav>\n"
        "</body></html>"
    )


def _build_failures_html(failures):
    lis = []
    for item in failures:
        url = item.get("url") or ""
        err = item.get("error") or "unknown error"
        lis.append(f"<li><a href={quoteattr(url)}>{xml_escape(url)}</a> &mdash; {xml_escape(err)}</li>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        "<head><title>Failures</title></head>\n"
        "<body><h1>Articles that could not be included</h1><ul>" + "".join(lis) + "</ul></body></html>"
    )
