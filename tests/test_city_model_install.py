"""Private model import remains a fixed-entry, non-executing packaging boundary."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from tools.install_city_model import MODEL_ENTRY, read_model


def glb(document):
    chunk = json.dumps(document).encode()
    chunk += b" " * (-len(chunk) % 4)
    return struct.pack("<IIIII", 0x46546C67, 2, 20 + len(chunk), len(chunk), 0x4E4F534A) + chunk


class CityModelImportTests(unittest.TestCase):
    def package(self, root, model, extra=()):
        path = Path(root) / "city.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(MODEL_ENTRY, model)
            for name, data in extra:
                archive.writestr(name, data)
        return path

    def test_only_expected_entry_is_read_and_no_scripts_are_extracted(self):
        data = glb({"asset": {"version": "2.0"}, "buffers": [{"byteLength": 0}]})
        with tempfile.TemporaryDirectory() as root:
            package = self.package(root, data, [("../unexpected.txt", "never extract"), ("web/source/setup.py", "raise RuntimeError()")])
            self.assertEqual(read_model(package, expected_sha256=hashlib.sha256(data).hexdigest()), data)
            self.assertEqual([file.name for file in Path(root).iterdir()], ["city.zip"])

    def test_unreviewed_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "differs"):
                read_model(self.package(root, glb({"asset": {"version": "2.0"}})))

    def test_external_image_uri_is_rejected(self):
        data = glb({"asset": {"version": "2.0"}, "images": [{"uri": "https://example.com/private.png"}]})
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "external"):
                read_model(self.package(root, data), expected_sha256=hashlib.sha256(data).hexdigest())

    def test_duplicate_model_entry_is_rejected(self):
        import warnings
        data = glb({"asset": {"version": "2.0"}})
        with tempfile.TemporaryDirectory() as root, warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            package = self.package(root, data, [(MODEL_ENTRY, data)])
            with self.assertRaisesRegex(ValueError, "one bounded"):
                read_model(package, expected_sha256=hashlib.sha256(data).hexdigest())
