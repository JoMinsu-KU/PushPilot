"""Resurfacing changes one material while preserving private model geometry and markings."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools.clean_city_roads import BIN_CHUNK, JSON_CHUNK, clean_road_model, install

FIXTURE_BINARY = b"original-draco-and-textures"


def glb(document, binary=FIXTURE_BINARY, extra=b""):
    encoded = json.dumps(document).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    remainder = struct.pack("<II", len(binary), BIN_CHUNK) + binary + extra
    return struct.pack("<IIIII", 0x46546C67, 2, 20 + len(encoded) + len(remainder), len(encoded), JSON_CHUNK) + encoded + remainder


def split(data):
    length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + length]), data[20 + length:]


def fixture():
    return {"asset": {"version": "2.0", "generator": "Private fixture"},
            "buffers": [{"byteLength": len(FIXTURE_BINARY)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 8}],
            "images": [{"bufferView": 0, "mimeType": "image/webp"}],
            "textures": [{"source": 0}],
            "materials": [{"name": "asphalt_photo", "doubleSided": True,
                           "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "roughnessFactor": 0.9, "metallicFactor": 0}},
                          {"name": "mark_yellow", "pbrMetallicRoughness": {"baseColorFactor": [0.9, 0.7, 0.1, 1]}},
                          {"name": "mark_white"}, {"name": "paving_photo"}, {"name": "F_street0_e"}],
            "meshes": [{"primitives": [{"material": 0, "extensions": {"KHR_draco_mesh_compression": {"bufferView": 0}}}]}],
            "nodes": [{"name": "fixed.001", "mesh": 0}], "extensionsUsed": ["KHR_draco_mesh_compression"]}


class CleanCityRoadTests(unittest.TestCase):
    def clean(self, data):
        return clean_road_model(data, expected_sha256=hashlib.sha256(data).hexdigest())

    def test_only_road_pbr_changes_and_binary_and_unknown_chunks_remain_identical(self):
        original = fixture()
        extra = struct.pack("<II", 4, 0x53544554) + b"test"
        source = glb(original, extra=extra)
        result = self.clean(source)
        cleaned, after = split(result)
        self.assertEqual(after, split(source)[1])
        expected = copy.deepcopy(original)
        expected["materials"][0]["pbrMetallicRoughness"] = {
            "baseColorFactor": [((value / 255 + 0.055) / 1.055) ** 2.4 for value in (69, 76, 80)] + [1],
            "roughnessFactor": 0.95, "metallicFactor": 0}
        self.assertEqual(cleaned, expected)
        self.assertEqual(struct.unpack_from("<I", result, 8)[0], len(result))
        self.assertEqual(len(result) % 4, 0)

    def test_source_hash_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            clean_road_model(glb(fixture()))

    def test_incomplete_binary_chunk_is_rejected_even_with_matching_hash(self):
        data = bytearray(glb(fixture()))
        binary_offset = 20 + struct.unpack_from("<I", data, 12)[0]
        struct.pack_into("<I", data, binary_offset, 1000)
        with self.assertRaisesRegex(ValueError, "chunk"):
            self.clean(bytes(data))

    def test_external_assets_and_ambiguous_road_materials_are_rejected(self):
        for kind in ("images", "buffers"):
            document = fixture()
            document[kind][0]["uri"] = "https://example.com/asset"
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "self-contained"):
                self.clean(glb(document))
        for names in ([], [{"name": "asphalt_photo"}]):
            document = fixture()
            document["materials"] = names if not names else document["materials"] + names
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, "exactly one"):
                self.clean(glb(document))

    def test_wrong_version_and_unaligned_chunk_are_rejected(self):
        for offset, value in ((4, 1), (12, 3)):
            data = bytearray(glb(fixture()))
            struct.pack_into("<I", data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.clean(bytes(data))

    def test_install_is_idempotent_preserves_original_and_refuses_other_output(self):
        data = glb(fixture())
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.glb"
            output = Path(directory) / "clean.glb"
            source.write_bytes(data)
            result = install(source, output, expected_sha256=digest)
            self.assertEqual(source.read_bytes(), data)
            self.assertEqual(install(source, output, expected_sha256=digest), result)
            self.assertEqual(result["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, "separate"):
                install(source, source, expected_sha256=digest)
            output.write_bytes(b"another private asset")
            with self.assertRaisesRegex(ValueError, "different"):
                install(source, output, expected_sha256=digest)
            self.assertEqual(output.read_bytes(), b"another private asset")
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["clean.glb", "original.glb"])

    def test_symbolic_link_destination_is_rejected(self):
        data = glb(fixture())
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.glb"
            output = Path(directory) / "clean.glb"
            source.write_bytes(data)
            with patch.object(Path, "is_symlink", lambda path: path == output), self.assertRaisesRegex(ValueError, "symbolic"):
                install(source, output, expected_sha256=hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
