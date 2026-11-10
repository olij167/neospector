"""Guard the owner site's read-only catalogue verification transport."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import owner_site_http as site


class FakeHTTP:
    def __init__(self, data=b'{"version":"0.7.25-ux41"}', url=site.ORIGIN + site.ALLOWED[0]):
        self.data = io.BytesIO(data)
        self.url = url
        self.status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.data.read(n)
    def geturl(self): return self.url


class SiteHTTPTests(unittest.TestCase):
    def test_explicit_owner_identity_and_json(self):
        def reply(request, timeout):
            self.assertEqual(request.get_method(), 'GET')
            self.assertTrue(request.get_header('User-agent').startswith('NeospectorOwnerPublisher/'))
            self.assertEqual(request.get_header('Accept'), 'application/json')
            self.assertEqual(timeout, 12)
            return FakeHTTP()
        with patch.object(site, 'urlopen', side_effect=reply):
            self.assertEqual(site.site_json('/downloads/neospector/releases.json')['version'], '0.7.25-ux41')

    def test_reject_unexpected_or_untrusted_site_paths(self):
        for p in ('https://evil.invalid', '//evil.invalid', '/admin', '/downloads/neospector/files/latest/linux', '/downloads/neospector/releases.json?token=1'):
            with self.subTest(path=p), self.assertRaises(site.WebsiteReadError):
                site.site_json(p)

    def test_http_403_fail_closed(self):
        with patch.object(site, 'urlopen', side_effect=HTTPError(site.ORIGIN + site.ALLOWED[0], 403, 'Forbidden', {'CF-Ray':'xyz-ABC'}, None)):
            with self.assertRaisesRegex(site.WebsiteReadError, 'HTTP 403 Forbidden.*Cloudflare Ray ID'):
                site.site_json(site.ALLOWED[0])

    def test_reject_external_redirect(self):
        with patch.object(site, 'urlopen', return_value=FakeHTTP(url='https://evil.invalid/releases.json')):
            with self.assertRaisesRegex(site.WebsiteReadError, 'redirected outside'):
                site.site_json(site.ALLOWED[0])

    def test_reject_oversize_json(self):
        with patch.object(site, 'urlopen', return_value=FakeHTTP(b'X'*100_001)):
            with self.assertRaisesRegex(site.WebsiteReadError, 'exceeded'):
                site.site_json(site.ALLOWED[0])

    def test_reject_html_while_expecting_json(self):
        with patch.object(site, 'urlopen', return_value=FakeHTTP(b'<html>error</html>')):
            with self.assertRaisesRegex(site.WebsiteReadError, 'valid JSON'):
                site.site_json(site.ALLOWED[0])

    def test_sized_read_and_nonobject_json(self):
        with patch.object(site, 'urlopen', return_value=FakeHTTP(b'[]')):
            with self.assertRaisesRegex(site.WebsiteReadError, 'unexpected JSON structure'):
                site.site_json(site.ALLOWED[0])

    def test_permitted_changelog_list(self):
        with patch.object(site, 'urlopen', return_value=FakeHTTP(b'[]',url=site.ORIGIN+'/downloads/neospector/changelog.json')):
            self.assertEqual(site.site_json('/downloads/neospector/changelog.json'), [])


if __name__ == '__main__': unittest.main()
