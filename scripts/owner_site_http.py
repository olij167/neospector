#!/usr/bin/env python3
"""Read-only public Neospector website validation for the Owner Publisher.

Cloudflare may reject Python's default urllib User-Agent. All owner-facing
website reads use one clearly named, unprivileged client and fail closed on
HTTP errors, unexpected redirects, oversized responses, or invalid JSON.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HOST = 'omne.space'
ORIGIN = 'https://' + HOST
USER_AGENT = 'NeospectorOwnerPublisher/1.0 (+https://omne.space/downloads/neospector)'
ALLOWED = (
    '/downloads/neospector/releases.json',
    '/downloads/neospector/changelog.json',
    '/neospector/updates/installers.json',
    '/neospector/updates/stable.json',
)


class WebsiteReadError(OSError):
    """The public release state could not be independently verified."""


def site_bytes(path: str, *, timeout: int = 12, max_bytes: int = 100_000) -> bytes:
    if path not in ALLOWED:
        raise WebsiteReadError('Refusing unexpected website validation path: ' + repr(path))
    if max_bytes < 1 or max_bytes > 1_000_000:
        raise ValueError('Website validation response limit is invalid')
    url = ORIGIN + path
    req = Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/json',
        'Cache-Control': 'no-cache',
    }, method='GET')
    try:
        with urlopen(req, timeout=timeout) as resp:
            destination = urlsplit(resp.geturl())
            if destination.scheme != 'https' or destination.hostname != HOST:
                raise WebsiteReadError('Website validation redirected outside trusted origin')
            if getattr(resp, 'status', 200) != 200:
                raise WebsiteReadError('Unexpected HTTP status while checking ' + path)
            body = resp.read(max_bytes + 1)
    except HTTPError as exc:
        cf_ray = (exc.headers.get('CF-Ray') if exc.headers else None)
        suffix = (' (Cloudflare Ray ID: ' + cf_ray[:100] + ')') if cf_ray else ''
        if exc.code == 403:
            raise WebsiteReadError(
                'HTTP 403 Forbidden checking ' + url + suffix +
                '. The public catalogue was not verified. Test with curl and review '
                'Cloudflare security events or route permissions if it remains blocked.'
            ) from exc
        raise WebsiteReadError('HTTP ' + str(exc.code) + ' checking ' + url + suffix) from exc
    except URLError as exc:
        raise WebsiteReadError('Website validation network error checking ' + url + ': ' + str(exc.reason)) from exc
    if len(body) > max_bytes:
        raise WebsiteReadError('Website validation JSON exceeded the allowed response size')
    return body


def site_json(path: str, *, timeout: int = 12, max_bytes: int = 100_000):
    try:
        result = json.loads(site_bytes(path, timeout=timeout, max_bytes=max_bytes))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WebsiteReadError('Website validation endpoint did not return valid JSON: ' + path) from exc
    if path != '/downloads/neospector/changelog.json' and not isinstance(result, dict):
        raise WebsiteReadError('Website validation endpoint returned unexpected JSON structure: ' + path)
    return result


if __name__ == '__main__':
    try:
        live = site_json('/downloads/neospector/releases.json')
        print('WEBSITE CATALOGUE OK — published version:', live.get('version', 'unknown'))
        print('Release stage:', live.get('release_stage', 'legacy'))
    except WebsiteReadError as exc:
        print('WEBSITE CHECK BLOCKED:', exc)
        raise SystemExit(2)
