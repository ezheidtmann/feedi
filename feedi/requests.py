import functools
import ipaddress
import socket
import urllib.parse

import requests

USER_AGENT = "feedi/0.1.0 (+https://github.com/facundoolano/feedi)"
TIMEOUT_SECONDS = 5
TIMEOUT_SLOWER = 10

requests = requests.Session()
requests.headers.update({"User-Agent": USER_AGENT})

# always use a default timeout
requests.get = functools.partial(requests.get, timeout=TIMEOUT_SECONDS)


class UnsafeURLError(ValueError):
    "Raised when a URL is refused because its scheme or resolved host is not safe to fetch."


def _is_private_ip(ip):
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def _is_private_address(host):
    # Literal IPs go through ipaddress directly; this catches IPs disguised as hostnames
    # (e.g. http://127.0.0.1/, http://0x7f000001/-style would still need a real resolver).
    try:
        ip = ipaddress.ip_address(host)
        return _is_private_ip(ip)
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # DNS resolution failed; don't preemptively block. The actual fetch will fail
        # downstream if the host is genuinely unreachable.
        return False

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if _is_private_ip(ip):
            return True
    return False


def _ssrf_guard_enabled():
    # httpretty (used in tests) resolves mocked hostnames to 127.0.0.1, which would trip
    # the private-IP check. Let the test/dev config opt out.
    try:
        import flask

        if flask.current_app.config.get("DISABLE_SSRF_GUARD"):
            return False
    except (RuntimeError, ImportError):
        pass
    return True


def safe_get(url, **kwargs):
    """
    Fetch a URL only if its scheme is http(s) and the resolved host is a public address.
    Used as the entry point for any URL that originated from user input or extracted page
    content, to avoid SSRF against internal services.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"unsupported scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("missing host")
    if _ssrf_guard_enabled() and _is_private_address(host):
        raise UnsafeURLError(f"refusing to fetch private/unresolvable host: {host!r}")

    kwargs.setdefault("timeout", TIMEOUT_SECONDS)
    return requests.get(url, **kwargs)
