"""Verify the public-source release boundary using isolated local Git fixtures."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import warnings
import zipfile


_SPEC = importlib.util.spec_from_file_location("build_release", Path(__file__).resolve().parents[1] / "tools" / "build_release.py")
release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release)


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "app"
        self.root.mkdir()
        self.output = self.root.parent / "source.zip"
        self.git("init", "--quiet")
        # Fixture-only identity: never changes user or application configuration.
        self.git("config", "user.name", "Release Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write("README.md", "Public source fixture.\n")
        self.write("backend/main.py", "value = 1\n")
        self.write(".gitignore", ".env\nruntime/\n")
        self.commit()

    def git(self, *args, input=None):
        result = subprocess.run(["git", "-C", str(self.root), *args], input=input, capture_output=True, check=True)
        return result.stdout

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "Fixture source")

    def rewrite_zip(self, transform):
        with zipfile.ZipFile(self.output) as source:
            entries = [(info, source.read(info)) for info in source.infolist()]
        with zipfile.ZipFile(self.output, "w") as target:
            for info, payload in entries:
                target.writestr(info, transform(info.filename, payload))

    def test_clean_head_manifest_and_ignored_files(self):
        self.write(".env", "EXAMPLE_PRIVATE_VALUE=fixture\n")
        self.write("runtime/local.json", "{}")
        manifest = release.build_release(self.root, self.output)
        self.assertEqual(manifest["git_head"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertTrue(manifest["public_code_only"])
        self.assertEqual(manifest, release.verify_release(self.output))
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), {"README.md", "backend/main.py", ".gitignore", release.MANIFEST_PATH})

    def test_modified_staged_and_untracked_files_fail(self):
        for state in ("modified", "staged", "untracked"):
            with self.subTest(state=state):
                if state == "untracked":
                    self.write("new.txt", "untracked")
                else:
                    self.write("backend/main.py", "value = 2\n")
                    if state == "staged":
                        self.git("add", "backend/main.py")
                with self.assertRaisesRegex(release.ReleaseError, "Commit or remove"):
                    release.build_release(self.root, self.output)
                self.git("reset", "--hard", "--quiet", "HEAD")
                (self.root / "new.txt").unlink(missing_ok=True)

    def test_output_inside_repo_and_existing_output_fail(self):
        with self.assertRaisesRegex(release.ReleaseError, "outside"):
            release.build_release(self.root, self.root / "source.zip")
        self.output.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(release.ReleaseError, "already exists"):
            release.build_release(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"do not overwrite")

    def test_private_tracked_files_fail_even_outside_allowlist(self):
        for name in ("backend/.env.production", "deploy/settings.local.json", "secrets/key.txt", "archive/private.key", "runtime/state.json"):
            with self.subTest(name=name):
                self.write(name, "fixture")
                self.git("add", "--force", name)
                self.git("commit", "--quiet", "-m", "Fixture private path")
                with self.assertRaises(release.ReleaseError):
                    release.build_release(self.root, self.output)
                self.git("reset", "--hard", "--quiet", "HEAD~1")

    def test_env_example_allowed_and_nonallowlisted_sources_excluded(self):
        self.write(".env.example", "EXAMPLE_VALUE=\n")
        self.write("CONTRIBUTING.md", "Public development guide.\n")
        self.write("reference/image.txt", "Historical source outside application layout")
        self.commit()
        manifest = release.build_release(self.root, self.output)
        paths = {entry["path"] for entry in manifest["files"]}
        self.assertIn(".env.example", paths)
        self.assertIn("CONTRIBUTING.md", paths)
        self.assertNotIn("reference/image.txt", paths)

    def test_git_symlink_entry_rejected_without_os_symlink_permission(self):
        object_id = self.git("hash-object", "-w", "--stdin", input=b"../outside.txt").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", "120000", object_id, "backend/link")
        self.git("commit", "--quiet", "-m", "Fixture symlink")
        # Checkout may materialize symlinks as text on Windows; the Git mode is authoritative.
        self.git("checkout", "--", "backend/link")
        with self.assertRaisesRegex(release.ReleaseError, "Symlinks"):
            release.build_release(self.root, self.output)

    def test_tampered_payload_rejected(self):
        release.build_release(self.root, self.output)
        self.rewrite_zip(lambda name, payload: payload.replace(b"1", b"9") if name == "backend/main.py" else payload)
        with self.assertRaisesRegex(release.ReleaseError, "SHA-256"):
            release.verify_release(self.output)

    def test_unsafe_archive_paths_rejected_without_extraction(self):
        for name in ("../escape.py", "/absolute.py", "C:/drive.py", "backend\\escape.py", "backend/./file.py", "backend/CON.txt"):
            with self.subTest(name=name):
                release.build_release(self.root, self.output, overwrite=True)
                with zipfile.ZipFile(self.output, "a") as archive:
                    # Windows ZipInfo normalizes backslashes on write. Patch
                    # both raw ZIP headers to exercise the original-name gate.
                    archive.writestr(name.replace("\\", "/"), b"fixture")
                if "\\" in name:
                    self.output.write_bytes(self.output.read_bytes().replace(name.replace("\\", "/").encode(), name.encode()))
                with self.assertRaisesRegex(release.ReleaseError, "Unsafe"):
                    release.verify_release(self.output)
        self.assertFalse((self.root.parent / "escape.py").exists())

    def test_duplicate_and_case_colliding_archive_names_rejected(self):
        for name in ("README.md", "readme.md"):
            with self.subTest(name=name):
                release.build_release(self.root, self.output, overwrite=True)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(self.output, "a") as archive:
                        archive.writestr(name, b"fixture")
                with self.assertRaisesRegex(release.ReleaseError, "Duplicate or colliding"):
                    release.verify_release(self.output)

    def test_archive_symlink_rejected(self):
        release.build_release(self.root, self.output)
        info = zipfile.ZipInfo("backend/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.output, "a") as archive:
            archive.writestr(info, b"../outside.txt")
        with self.assertRaisesRegex(release.ReleaseError, "symlinks"):
            release.verify_release(self.output)

    def test_archive_size_limits(self):
        release.build_release(self.root, self.output)
        with self.assertRaisesRegex(release.ReleaseError, "size limit"):
            release.verify_release(self.output, max_entry_size=1)
        with self.assertRaisesRegex(release.ReleaseError, "total size limit"):
            release.verify_release(self.output, max_total_size=1)
        with self.assertRaisesRegex(release.ReleaseError, "entry count"):
            release.verify_release(self.output, max_entries=1)

    def test_missing_or_duplicate_manifest_keys_fail(self):
        release.build_release(self.root, self.output)
        self.rewrite_zip(lambda name, payload: b'{"schema_version":"x","schema_version":"y"}' if name == release.MANIFEST_PATH else payload)
        with self.assertRaisesRegex(release.ReleaseError, "Duplicate JSON"):
            release.verify_release(self.output)

    def test_cli_verify(self):
        release.build_release(self.root, self.output)
        script = Path(release.__file__)
        result = subprocess.run([__import__("sys").executable, str(script), "--verify", str(self.output)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["status"], "verified")


if __name__ == "__main__":
    unittest.main()
