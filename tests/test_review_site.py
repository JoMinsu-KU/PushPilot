"""Verify the public review artifact without providers, equipment or services."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("build_review_site", ROOT / "tools/build_review_site.py")
site = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(site)


class ReviewSiteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "repo"
        self.output = self.directory / "public-site"
        for name in {site.HTML_SOURCE, site.RECORD_SOURCE, site.FONT_SOURCE, site.LICENSE_SOURCE, site.BRAND_SOURCE, *site.LINKS.values()}:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.original = (self.root / site.HTML_SOURCE).read_bytes()
        self.brand_uri = "data:image/png;base64," + base64.b64encode((self.root / site.BRAND_SOURCE).read_bytes()).decode("ascii")

    def test_only_explicit_html_font_and_license_are_published(self):
        for name in (".env", "runtime/robot.json", "docs/assets/private.jpg", "backend/main.py"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("PRIVATE_FIXTURE", encoding="utf-8")
        result = site.build_review_site(self.root, self.output)
        self.assertEqual(set(result), site.OUTPUT_FILES)
        self.assertEqual({p.relative_to(self.output).as_posix() for p in self.output.rglob("*") if p.is_file()}, site.OUTPUT_FILES)
        self.assertEqual((self.output / "fonts/PretendardVariable.woff2").read_bytes(), (self.root / site.FONT_SOURCE).read_bytes())
        self.assertEqual((self.output / "fonts/OFL.txt").read_bytes(), (self.root / site.LICENSE_SOURCE).read_bytes())
        self.assertIn("SIL OPEN FONT LICENSE", (self.output / "fonts/OFL.txt").read_text(encoding="utf-8"))
        self.assertEqual((self.root / site.HTML_SOURCE).read_bytes(), self.original)
        self.assertTrue(all(not p.is_symlink() and p.stat().st_nlink == 1 for p in self.output.rglob("*") if p.is_file()))

    def test_original_json_images_and_csp_are_preserved(self):
        site.build_review_site(self.root, self.output)
        source = self.original.decode("utf-8")
        hosted = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertEqual(site._DATA_SCRIPT.findall(source), site._DATA_SCRIPT.findall(hosted))
        record = json.loads(dict(site._DATA_SCRIPT.findall(hosted))["archived-record"])
        self.assertEqual(record, json.loads((self.root / site.RECORD_SOURCE).read_bytes()))
        images = json.loads(dict(site._DATA_SCRIPT.findall(hosted))["fixture-images"])
        for name, data in images.items():
            self.assertEqual(hashlib.sha256(base64.b64decode(data)).hexdigest(), record["fixture_sha256"][name])
        self.assertEqual(re.search(r'<meta http-equiv="Content-Security-Policy"[^>]+>', source)[0], re.search(r'<meta http-equiv="Content-Security-Policy"[^>]+>', hosted)[0])
        self.assertIn("connect-src 'none'", hosted)
        source_scripts = re.findall(r"<script(?:>|\s[^>]*>)([\s\S]*?)</script>", source)
        self.assertEqual(source_scripts, re.findall(r"<script(?:>|\s[^>]*>)([\s\S]*?)</script>", hosted))

    def test_navigation_uses_canonical_repository_and_self_hosted_font(self):
        site.build_review_site(self.root, self.output)
        hosted = (self.output / "index.html").read_text(encoding="utf-8")
        for _, target in site._HREF.findall(hosted):
            self.assertTrue(target.startswith("#") or target == self.brand_uri or target in {site.REPOSITORY_URL + path for path in site.LINKS.values()})
        for path in site.LINKS.values():
            self.assertIn(site.REPOSITORY_URL + path, hosted)
        self.assertIn("url('fonts/PretendardVariable.woff2')", hosted)
        self.assertNotIn(site.FONT_REFERENCE, hosted)

    def test_header_and_favicon_embed_the_identical_approved_png_without_extra_files(self):
        site.build_review_site(self.root, self.output)
        hosted = (self.output / "index.html").read_text(encoding="utf-8")
        icon = re.search(r'<link rel="icon" type="image/png" href="([^"]+)">', hosted)[1]
        header = re.search(r"\.brand::before\{[^}]*background:url\('([^']+)'\)", hosted)[1]
        self.assertEqual(icon, header)
        self.assertEqual(icon, self.brand_uri)
        embedded = base64.b64decode(icon.split(",", 1)[1], validate=True)
        self.assertEqual(embedded, (self.root / site.BRAND_SOURCE).read_bytes())
        self.assertEqual(hashlib.sha256(embedded).hexdigest(), site.BRAND_SHA256)
        self.assertEqual(set(p.relative_to(self.output).as_posix() for p in self.output.rglob("*") if p.is_file()), site.OUTPUT_FILES)

    def test_rejects_changed_brand_bytes_missing_or_divergent_branding_and_external_icons(self):
        uri = self.brand_uri.encode("ascii")
        mutations = (
            (site.BRAND_SOURCE, lambda data: data + b"changed", "Pinned brand bytes"),
            (site.HTML_SOURCE, lambda data: data.replace(uri, b"data:image/png;base64,AAAA", 1), "pinned inline brand favicon"),
            (site.HTML_SOURCE, lambda data: data.replace(uri, b"data:image/png;base64,AAAA", 2), "pinned inline brand favicon"),
            (site.HTML_SOURCE, lambda data: data.replace(uri, b"https://example.invalid/mark.png", 1), "pinned inline brand favicon"),
            (site.HTML_SOURCE, lambda data: data.replace(b"</head>", b'<link rel="stylesheet" href="https://example.invalid/style.css"></head>'), "pinned inline brand favicon"),
            (site.HTML_SOURCE, lambda data: data.replace(b"</head>", b'<link rel="icon" type="image/png" href="' + uri + b'"></head>'), "Exactly one pinned brand"),
            (site.HTML_SOURCE, lambda data: data.replace(b".brand::before{", b".unrelated::before{", 1), "header must use"),
        )
        for name, change, message in mutations:
            path = self.root / name
            original = path.read_bytes()
            with self.subTest(name=name, message=message):
                path.write_bytes(change(original))
                with self.assertRaisesRegex(site.ReviewSiteError, message):
                    site.build_review_site(self.root, self.output)
                self.assertFalse(self.output.exists())
                path.write_bytes(original)

    def test_rejects_nonempty_output_and_output_inside_source(self):
        self.output.mkdir()
        existing = self.output / "keep.txt"
        existing.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(site.ReviewSiteError, "not an empty"):
            site.build_review_site(self.root, self.output)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
        for output in (self.root, self.root.parent, self.root / "docs/review/site", self.root / "dist/review-site/nested"):
            with self.subTest(output=output), self.assertRaisesRegex(site.ReviewSiteError, "outside"):
                site.build_review_site(self.root, output)

    def test_ignored_dist_target_and_empty_existing_directory_are_allowed(self):
        output = self.root / "dist/review-site"
        output.mkdir(parents=True)
        self.assertEqual(set(site.build_review_site(self.root, output)), site.OUTPUT_FILES)

    def test_rejects_modified_font_record_images_and_new_resource(self):
        mutations = (
            (site.FONT_SOURCE, lambda data: data + b"x", "Pinned"),
            (site.LICENSE_SOURCE, lambda data: data + b"x", "Pinned"),
            (site.HTML_SOURCE, lambda data: data.replace(b'"evaluated_on": "2026-10-27"', b'"evaluated_on": "2026-10-28"', 1), "judgments differ"),
            (site.HTML_SOURCE, lambda data: data.replace(b'"before":"iVBOR', b'"before":"jVBOR', 1), "fixture hash mismatch"),
            (site.HTML_SOURCE, lambda data: data.replace(b"connect-src 'none'", b"connect-src 'self'"), "no-connection"),
            (site.HTML_SOURCE, lambda data: data.replace(b"</head>", b'<script src="/api/request"></script></head>'), "inline"),
            (site.HTML_SOURCE, lambda data: data.replace(b"../../README.md", b"../../runtime/private.json"), "Unexpected source link"),
        )
        for name, change, message in mutations:
            path = self.root / name
            original = path.read_bytes()
            with self.subTest(name=name, message=message):
                path.write_bytes(change(original))
                with self.assertRaisesRegex(site.ReviewSiteError, message):
                    site.build_review_site(self.root, self.output)
                self.assertFalse(self.output.exists())
                path.write_bytes(original)

    def test_rejects_symlink_input_and_output(self):
        linked = self.directory / "linked-output"
        try:
            linked.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symbolic links requires unavailable local permission.")
        with self.assertRaisesRegex(site.ReviewSiteError, "Symlinks"):
            site.build_review_site(self.root, linked / "child")
        font = self.root / site.FONT_SOURCE
        font.unlink()
        font.symlink_to(ROOT / site.FONT_SOURCE)
        with self.assertRaisesRegex(site.ReviewSiteError, "Symlinks"):
            site.build_review_site(self.root, self.output)


if __name__ == "__main__":
    unittest.main()
