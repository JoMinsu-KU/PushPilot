"""Build and verify a public-source ZIP from a clean local Git commit.

This tool never connects to a server, imports robot code, or starts a service.
The allowlist is a packaging boundary, not a substitute for reviewing source
contents for credentials and third-party publication rights.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
import zipfile


SCHEMA_VERSION = "pushpilot.source-release.v1"
MANIFEST_PATH = "release-manifest.json"
ALLOWED_DIRECTORIES = frozenset({
    "frontend", "backend", "contracts", "prompts", "tests", "deploy", "docs", "tools",
})
ALLOWED_ROOT_FILES = frozenset({
    "README.md", "AGENTS.md", "CONTRIBUTING.md", "CONTRIBUTIONS.md", "THIRD_PARTY_NOTICES.md",
    ".gitignore", ".gitattributes", ".env.example", "pyproject.toml", "requirements.lock",
})
FORBIDDEN_PARTS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", ".cache", "secrets", "credentials",
    "runtime", "logs", "uploads", "dist", "build",
})
MAX_TOTAL_SIZE = 128 * 1024 * 1024
MAX_ENTRY_SIZE = 32 * 1024 * 1024
MAX_ENTRIES = 10_000
MAX_MANIFEST_SIZE = 4 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_HEAD = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_WINDOWS_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z", re.I)


class ReleaseError(ValueError):
    """A release does not satisfy the source-package policy."""


def _git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, check=False,
    )
    if result.returncode:
        raise ReleaseError(f"Git command failed: git {' '.join(args[:2])}. Ensure this is a local repository with a committed HEAD.")
    return result.stdout


def _safe_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ReleaseError("Unsafe archive path.")
    parts = name.split("/")
    for part in parts:
        if (
            not part or part in {".", ".."} or part[-1:] in {".", " "}
            or any(ord(character) < 32 or character in '<>:"|?*' for character in part)
            or _WINDOWS_DEVICE.fullmatch(part)
        ):
            raise ReleaseError(f"Unsafe archive path: {name!r}.")
    return unicodedata.normalize("NFC", name).casefold()


def _check_public_path(name: str) -> None:
    _safe_name(name)
    parts = name.split("/")
    for part in parts:
        lower = part.lower()
        if lower in FORBIDDEN_PARTS:
            raise ReleaseError(f"Forbidden source path: {name}.")
        if (
            (lower.startswith(".env") and lower != ".env.example")
            or lower.endswith(".env") or ".local." in lower or lower.endswith(".local")
            or lower.startswith(("secrets.", "credentials.", "id_rsa", "id_ed25519"))
            or lower in {"service_account.json", "service-account.json"}
            or lower.endswith((".pem", ".key", ".p12", ".pfx", ".keystore", ".kdbx", ".jks"))
        ):
            raise ReleaseError(f"Private configuration or credential path is forbidden: {name}.")


def _allowed(name: str) -> bool:
    parts = name.split("/")
    return (len(parts) == 1 and name in ALLOWED_ROOT_FILES) or (
        len(parts) > 1 and parts[0] in ALLOWED_DIRECTORIES
    )


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build_release(repo_root: str | Path, output: str | Path, *, overwrite: bool = False) -> dict:
    """Package committed allowlisted blobs; reject any nonignored dirty state.

    Ignored local files are never read. Tracked forbidden paths and symlinks
    anywhere in HEAD fail the build, including paths outside the allowlist.
    """
    root = Path(repo_root).resolve()
    output_path = Path(output).absolute()
    if output_path.is_symlink():
        raise ReleaseError("The output must not be a symbolic link.")
    output_path = output_path.resolve()
    if output_path == root or root in output_path.parents:
        raise ReleaseError("The release output must be outside the repository.")
    if output_path.suffix.lower() != ".zip":
        raise ReleaseError("The release output must use a .zip extension.")
    if output_path.exists() and not overwrite:
        raise ReleaseError("The output already exists; choose a new release path.")
    if not output_path.parent.is_dir():
        raise ReleaseError("The release output directory must already exist.")
    actual_root = Path(_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    if actual_root != root:
        raise ReleaseError("Use the application repository root, not a parent or child directory.")
    head = _git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if not _GIT_HEAD.fullmatch(head):
        raise ReleaseError("The committed Git HEAD is invalid.")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all", "-z"):
        raise ReleaseError("Commit or remove all staged, modified, and nonignored untracked files before building a release.")

    blobs: list[tuple[str, str]] = []
    normalized_names: set[str] = set()
    tree = _git(root, "ls-tree", "-r", "-z", "--full-tree", head)
    for record in tree.split(b"\x00"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split(" ")
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ReleaseError("Tracked source paths must be valid UTF-8.") from error
        key = _safe_name(name)
        _check_public_path(name)
        if key in normalized_names:
            raise ReleaseError("Tracked paths collide on a case-insensitive filesystem.")
        normalized_names.add(key)
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ReleaseError(f"Symlinks, submodules, and special files are forbidden: {name}.")
        if _allowed(name):
            blobs.append((name, object_id))
    if not blobs:
        raise ReleaseError("No allowlisted source files exist in the committed HEAD.")
    if len(blobs) + 1 > MAX_ENTRIES:
        raise ReleaseError("The source release has too many entries.")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "release_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + head[:12],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_head": head,
        "public_code_only": True,
        "scope": "committed_allowlisted_source",
        "content_review": "required_before_publication",
        "files": [],
    }
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".pushpilot-release-", suffix=".zip", dir=output_path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        total = 0
        with zipfile.ZipFile(temporary_path, "w") as archive:
            for name, object_id in sorted(blobs):
                size = int(_git(root, "cat-file", "-s", object_id).strip())
                if size > MAX_ENTRY_SIZE or total + size > MAX_TOTAL_SIZE:
                    raise ReleaseError("The source release exceeds its size limit.")
                payload = _git(root, "cat-file", "blob", object_id)
                if len(payload) != size:
                    raise ReleaseError("The committed blob size changed unexpectedly.")
                total += size
                manifest["files"].append({"path": name, "size_bytes": size, "sha256": hashlib.sha256(payload).hexdigest()})
                archive.writestr(_zip_info(name), payload)
            manifest["file_count"] = len(manifest["files"])
            manifest["total_size_bytes"] = total
            encoded_manifest = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
            if len(encoded_manifest) > MAX_MANIFEST_SIZE or total + len(encoded_manifest) > MAX_TOTAL_SIZE:
                raise ReleaseError("The source release manifest exceeds its size limit.")
            archive.writestr(_zip_info(MANIFEST_PATH), encoded_manifest)
        verify_release(temporary_path)
        if overwrite:
            os.replace(temporary_path, output_path)
            temporary_path = None
        else:
            created = False
            try:
                with output_path.open("xb") as target:
                    created = True
                    with temporary_path.open("rb") as source:
                        shutil.copyfileobj(source, target)
            except FileExistsError as error:
                raise ReleaseError("The output already exists; choose a new release path.") from error
            except BaseException:
                if created:
                    output_path.unlink(missing_ok=True)
                raise
        return manifest
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseError("Duplicate JSON keys in the release manifest.")
        result[key] = value
    return result


def verify_release(
    archive_path: str | Path, *, max_total_size: int = MAX_TOTAL_SIZE,
    max_entry_size: int = MAX_ENTRY_SIZE, max_entries: int = MAX_ENTRIES,
) -> dict:
    """Validate paths, metadata, sizes, and file hashes without extracting files.

    SHA-256 detects corruption against this manifest. It does not authenticate
    the publisher or attest that a Git commit exists in a trusted repository.
    """
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            entries = archive.infolist()
            if not entries or len(entries) > max_entries:
                raise ReleaseError("The archive entry count is invalid.")
            normalized_names: set[str] = set()
            total = 0
            for info in entries:
                # ZipInfo can normalize backslashes on Windows and truncate at
                # NUL. Validate the original header name before that aliasing.
                _safe_name(info.orig_filename)
                if info.orig_filename != info.filename:
                    raise ReleaseError("Unsafe archive path normalization.")
                key = _safe_name(info.filename)
                if key in normalized_names:
                    raise ReleaseError("Duplicate or colliding archive entries are forbidden.")
                normalized_names.add(key)
                if info.filename != MANIFEST_PATH:
                    _check_public_path(info.filename)
                    if not _allowed(info.filename):
                        raise ReleaseError(f"Archive entry is outside the source allowlist: {info.filename}.")
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if info.is_dir() or file_type not in {0, stat.S_IFREG}:
                    raise ReleaseError("Archive symlinks, directories, and special files are forbidden.")
                if info.flag_bits & 1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise ReleaseError("Encrypted or unsupported archive entries are forbidden.")
                limit = min(max_entry_size, MAX_MANIFEST_SIZE) if info.filename == MANIFEST_PATH else max_entry_size
                if info.file_size < 0 or info.file_size > limit:
                    raise ReleaseError("The archive entry exceeds its size limit.")
                total += info.file_size
                if total > max_total_size:
                    raise ReleaseError("The archive exceeds its total size limit.")
            if MANIFEST_PATH not in {info.filename for info in entries}:
                raise ReleaseError("The release manifest is missing.")
            manifest = json.loads(archive.read(MANIFEST_PATH), object_pairs_hook=_json_object)
            if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
                raise ReleaseError("Unsupported release manifest schema.")
            if (
                manifest.get("public_code_only") is not True
                or manifest.get("scope") != "committed_allowlisted_source"
                or not isinstance(manifest.get("git_head"), str)
                or not _GIT_HEAD.fullmatch(manifest["git_head"])
                or not isinstance(manifest.get("release_id"), str) or not manifest["release_id"]
            ):
                raise ReleaseError("The release identity or scope is invalid.")
            files = manifest.get("files")
            if not isinstance(files, list) or not files:
                raise ReleaseError("The manifest file list is invalid.")
            expected: dict[str, dict] = {}
            for entry in files:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise ReleaseError("Invalid manifest file entry.")
                name = entry["path"]
                _check_public_path(name)
                if not _allowed(name) or name in expected:
                    raise ReleaseError("Invalid or duplicate manifest source path.")
                if type(entry.get("size_bytes")) is not int or entry["size_bytes"] < 0:
                    raise ReleaseError("Invalid manifest file size.")
                if not isinstance(entry.get("sha256"), str) or not _SHA256.fullmatch(entry["sha256"]):
                    raise ReleaseError("Invalid manifest SHA-256.")
                expected[name] = entry
            actual_names = {info.filename for info in entries if info.filename != MANIFEST_PATH}
            if set(expected) != actual_names:
                raise ReleaseError("The archive contents do not match the manifest file list.")
            payload_total = 0
            for name, entry in expected.items():
                info = archive.getinfo(name)
                if info.file_size != entry["size_bytes"]:
                    raise ReleaseError(f"File size mismatch: {name}.")
                digest = hashlib.sha256()
                actual_size = 0
                with archive.open(info) as source:
                    while chunk := source.read(64 * 1024):
                        actual_size += len(chunk)
                        if actual_size > max_entry_size or actual_size > entry["size_bytes"]:
                            raise ReleaseError("Decompressed content exceeds its declared size.")
                        digest.update(chunk)
                if actual_size != entry["size_bytes"] or digest.hexdigest() != entry["sha256"]:
                    raise ReleaseError(f"SHA-256 or file size mismatch: {name}.")
                payload_total += actual_size
            if type(manifest.get("file_count")) is not int or manifest["file_count"] != len(expected):
                raise ReleaseError("The manifest file count does not match.")
            if type(manifest.get("total_size_bytes")) is not int or manifest["total_size_bytes"] != payload_total:
                raise ReleaseError("The manifest total size does not match.")
            return manifest
    except ReleaseError:
        raise
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, NotImplementedError, RuntimeError, EOFError) as error:
        raise ReleaseError("Unable to read or verify the release archive.") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--output", type=Path, help="New ZIP path outside the application repository.")
    operation.add_argument("--verify", type=Path, help="Verify an existing ZIP without extracting it.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1], help="Application repository root (default: this script's parent project).")
    args = parser.parse_args(argv)
    try:
        manifest = verify_release(args.verify) if args.verify else build_release(args.repo_root, args.output)
    except ReleaseError as error:
        parser.exit(2, f"Release error: {error}\n")
    print(json.dumps({"status": "verified" if args.verify else "built", "release_id": manifest["release_id"], "git_head": manifest["git_head"], "file_count": manifest["file_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
