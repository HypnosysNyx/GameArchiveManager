"""RC2 preflight reads only a bounded header and never carves private data."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.probe_embedded_rar5 import preflight, main
from tests.test_integration import create_rar5_encryption_header


class EmbeddedRar5PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.host = self.root / "video.mp4"
        self.offset = len(b"synthetic video prefix")
        self.host.write_bytes(b"synthetic video prefix" +
                              create_rar5_encryption_header() +
                              b"synthetic trailing bytes")
        self.original = self.host.read_bytes()

    def test_detects_valid_encrypted_header_without_claiming_data_success(self):
        result = preflight(self.host, self.offset, disk_free_bytes=2 * 1024 ** 3)
        self.assertEqual(result["structure"], "VALID_ENCRYPTED")
        self.assertEqual(result["reason"], "VALID_ENCRYPTED")
        self.assertTrue(result["rar5_encrypted_header"])
        self.assertFalse(result["data_crc_verified"])
        self.assertFalse(result["password_verified"])
        self.assertFalse(result["carve_attempted"])
        self.assertTrue(result["can_reserve_full_tail_copy"])
        self.assertNotIn(str(self.host), repr(result))
        self.assertEqual(self.original, self.host.read_bytes())
        self.assertEqual([self.host], list(self.root.iterdir()))

    def test_false_candidate_and_corrupted_crc_are_rejected(self):
        result = preflight(self.host, self.offset + 1, disk_free_bytes=2 * 1024 ** 3)
        self.assertEqual(result["structure"], "INVALID_STRUCTURE")
        self.assertNotEqual(result["reason"], "VALID_ENCRYPTED")
        corrupted = bytearray(self.original)
        corrupted[self.offset + 8] ^= 1  # RAR5 header CRC byte
        self.host.write_bytes(corrupted)
        result = preflight(self.host, self.offset, disk_free_bytes=2 * 1024 ** 3)
        self.assertEqual(result["structure"], "INVALID_STRUCTURE")
        self.assertEqual(result["reason"], "INVALID_CRC")

    def test_offset_invalid_no_copy_or_io(self):
        for offset in (-1, 0, self.host.stat().st_size,
                       self.host.stat().st_size + 1):
            with self.subTest(offset=offset):
                with patch("analyzer.embedded_detector.EmbeddedArchiveDetector.validate_candidate") as parser:
                    result = preflight(self.host, offset, disk_free_bytes=0)
                    parser.assert_not_called()
                self.assertEqual(result["reason"], "OFFSET_OUT_OF_RANGE")
                self.assertFalse(result["carve_attempted"])
        self.assertEqual(self.original, self.host.read_bytes())

    def test_disk_insufficiency_report_is_not_password_or_corruption(self):
        result = preflight(self.host, self.offset, disk_free_bytes=0)
        self.assertEqual(result["structure"], "VALID_ENCRYPTED")
        self.assertFalse(result["can_reserve_full_tail_copy"])
        self.assertGreater(result["full_tail_copy_plus_reserve_bytes"], 0)
        self.assertFalse(result["password_verified"])
        self.assertFalse(result["data_crc_verified"])

    def test_nonexistent_and_non_regular_sources_fail_closed(self):
        self.assertEqual(preflight(self.root / "missing", self.offset)["reason"],
                         "SOURCE_READ_ERROR")
        self.assertEqual(preflight(self.root, self.offset)["reason"],
                         "SOURCE_NOT_REGULAR")

    def test_output_json_does_not_include_input_path_or_secret(self):
        from io import StringIO
        from contextlib import redirect_stdout
        output = StringIO()
        with redirect_stdout(output):
            status = main([str(self.host), "--offset", str(self.offset)])
        self.assertEqual(status, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["candidates"][0]["structure"], "VALID_ENCRYPTED")
        self.assertNotIn(str(self.host), output.getvalue())
        self.assertIn("unverified", payload["note"].lower())


if __name__ == "__main__":
    unittest.main()
