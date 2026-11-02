"""Package only the public, read-only recorded review for static hosting.

Uses the standard library only. No API, camera, backend or robot code is loaded.
Source HTML, archived responses and embedded fixture PNG bytes are not edited.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re


REPOSITORY_URL = "https://github.com/JoMinsu-KU/PushPilot/blob/main/"
HTML_SOURCE = "docs/review/index.html"
RECORD_SOURCE = "docs/evidence/synthetic-action-reviews-20261027.json"
FONT_SOURCE = "frontend/public/fonts/pretendard/PretendardVariable.woff2"
LICENSE_SOURCE = "frontend/public/fonts/pretendard/OFL.txt"
FONT_SHA256 = "9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4"
LICENSE_SHA256 = "d31ddd9f2bed32fd7e302a205cf2380ba0de6529152d239ef99cfb6f261bfc04"
FONT_REFERENCE = "../../" + FONT_SOURCE
LINKS = {
    "../../README.md": "README.md",
    "../../tools/action_review_fixtures.py": "tools/action_review_fixtures.py",
    "../DEMO.md": "docs/DEMO.md",
    "../META_API_CHECK.md": "docs/META_API_CHECK.md",
    "../evidence/README.md": "docs/evidence/README.md",
    "../evidence/synthetic-action-reviews-20261027.json": RECORD_SOURCE,
}
OUTPUT_FILES = frozenset({
    "index.html", "fonts/PretendardVariable.woff2", "fonts/OFL.txt", ".nojekyll",
})
_HREF = re.compile(r"\bhref=([\"'])(.*?)\1")
_DATA_SCRIPT = re.compile(r'<script type="application/json" id="([^"]+)">([\s\S]*?)</script>')


class ReviewSiteError(ValueError):
    """An input or output does not satisfy the narrow public-site boundary."""


def _reject_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ReviewSiteError(f"Symlinks and junctions are not allowed: {part}")


def _read(root: Path, name: str) -> bytes:
    path = root / name
    _reject_links(path)
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ReviewSiteError(f"Missing or unsafe public input: {name}")
    return path.read_bytes()


class _BoundaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.csp: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"iframe", "object", "embed", "form", "base", "link"}:
            raise ReviewSiteError(f"Unexpected resource or interactive boundary: {tag}")
        if any(key.startswith("on") for key in values) or "src" in values or "srcset" in values:
            raise ReviewSiteError("Only existing inline scripts and embedded fixture images are allowed.")
        if tag == "meta" and values.get("http-equiv", "").lower() == "content-security-policy":
            self.csp.append(values.get("content", ""))


def _validate_html(html: str) -> None:
    parser = _BoundaryParser()
    parser.feed(html)
    if len(parser.csp) != 1:
        raise ReviewSiteError("Exactly one original Content-Security-Policy is required.")
    directives = {part.strip() for part in parser.csp[0].split(";")}
    if not {"default-src 'none'", "connect-src 'none'", "base-uri 'none'", "form-action 'none'"} <= directives:
        raise ReviewSiteError("The original no-connection Content-Security-Policy must be preserved.")


def _validate_record(html: str, record_bytes: bytes) -> None:
    scripts = dict(_DATA_SCRIPT.findall(html))
    if set(scripts) != {"archived-record", "fixture-images"}:
        raise ReviewSiteError("Expected the two original embedded JSON records.")
    try:
        record = json.loads(scripts["archived-record"])
        images = json.loads(scripts["fixture-images"])
        if record != json.loads(record_bytes):
            raise ReviewSiteError("Embedded judgments differ from the original public record.")
        if set(images) != set(record["fixture_sha256"]):
            raise ReviewSiteError("Embedded fixture set differs from the public record.")
        for name, data in images.items():
            if hashlib.sha256(base64.b64decode(data, validate=True)).hexdigest() != record["fixture_sha256"][name]:
                raise ReviewSiteError(f"Embedded fixture hash mismatch: {name}")
    except (KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, ReviewSiteError):
            raise
        raise ReviewSiteError("Invalid archived record or fixture image.") from error


def build_review_site(repo_root: Path, output: Path) -> dict[str, str]:
    """Write a new allowlisted directory; reject existing nonempty outputs."""
    _reject_links(repo_root.absolute())
    root = repo_root.resolve(strict=True)
    _reject_links(output.absolute())
    destination = output.resolve()
    if root.is_relative_to(destination) or (
        destination.is_relative_to(root) and destination != root / "dist" / "review-site"
    ):
        raise ReviewSiteError("Output must be outside the repository or exactly dist/review-site.")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ReviewSiteError("Output already exists and is not an empty directory; nothing was changed.")

    source = _read(root, HTML_SOURCE).decode("utf-8")
    _validate_html(source)
    _validate_record(source, _read(root, RECORD_SOURCE))
    font = _read(root, FONT_SOURCE)
    license_text = _read(root, LICENSE_SOURCE)
    for name, data, expected in (
        (FONT_SOURCE, font, FONT_SHA256), (LICENSE_SOURCE, license_text, LICENSE_SHA256),
    ):
        if hashlib.sha256(data).hexdigest() != expected:
            raise ReviewSiteError(f"Pinned font/license bytes differ: {name}")

    def hosted_link(match: re.Match[str]) -> str:
        target = match[2]
        if target.startswith("#"):
            return match[0]
        if target not in LINKS:
            raise ReviewSiteError(f"Unexpected source link; review the allowlist: {target}")
        _read(root, LINKS[target])
        return f"href={match[1]}{REPOSITORY_URL}{LINKS[target]}{match[1]}"

    hosted = _HREF.sub(hosted_link, source)
    if hosted.count(FONT_REFERENCE) != 1:
        raise ReviewSiteError("Expected exactly one original self-hosted Pretendard reference.")
    hosted = hosted.replace(FONT_REFERENCE, "fonts/PretendardVariable.woff2")
    _validate_html(hosted)
    if _DATA_SCRIPT.findall(hosted) != _DATA_SCRIPT.findall(source):
        raise ReviewSiteError("Packaging changed an archived response or fixture payload.")
    files = {
        "index.html": hosted.encode("utf-8"),
        "fonts/PretendardVariable.woff2": font,
        "fonts/OFL.txt": license_text,
        ".nojekyll": b"",
    }
    if set(files) != OUTPUT_FILES:
        raise ReviewSiteError("Unexpected public artifact entry.")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="New directory outside the repo, or dist/review-site.")
    args = parser.parse_args()
    try:
        manifest = build_review_site(args.repo_root, args.output)
    except (ReviewSiteError, OSError) as error:
        parser.exit(1, f"Review site packaging failed: {error}\n")
    print(json.dumps({"output": str(args.output.resolve()), "sha256": manifest}, indent=2))


if __name__ == "__main__":
    main()
