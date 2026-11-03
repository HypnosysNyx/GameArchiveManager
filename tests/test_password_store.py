"""Regression tests for the Windows DPAPI-backed password library."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from password.session_store import PasswordStoreError, SessionPasswordStore


class PasswordStoreTests(unittest.TestCase):
    def test_missing_library_is_empty_and_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            self.assertEqual([], SessionPasswordStore(path).passwords())
            self.assertFalse(path.exists())

    def test_saved_passwords_are_available_to_a_new_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            values = ["fixture-password", "中文🔐", "Case", "case"]
            store = SessionPasswordStore(path)
            store.replace(values + ["fixture-password", ""])
            self.assertEqual(values, store.passwords())
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("fixture-password", raw)
            self.assertNotIn("中文", raw)
            self.assertEqual([], list(path.parent.glob(".passwords-*.tmp")))
            reloaded = SessionPasswordStore(path)
            self.assertEqual(values, reloaded.passwords())
            self.assertEqual(len(values), len(reloaded.candidates()))
            self.assertEqual(0, len(reloaded))

    def test_existing_version_one_library_remains_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            old_encrypted = SessionPasswordStore._protect(json.dumps(["legacy-password"]).encode("utf-8"))
            path.write_text(json.dumps({
                "version": 1,
                "protected_passwords": base64.b64encode(old_encrypted).decode("ascii"),
            }), encoding="utf-8")
            self.assertEqual(["legacy-password"], SessionPasswordStore(path).passwords())

    def test_corrupted_or_unsupported_library_is_not_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            invalid_payloads = [
                "{not-json",
                json.dumps({"version": 2, "protected_passwords": "AA=="}),
                json.dumps({"version": 1, "protected_passwords": "not@base64"}),
                json.dumps({"version": 1, "protected_passwords": None}),
                json.dumps(["not-a-library"]),
            ]
            for raw in invalid_payloads:
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaises(PasswordStoreError):
                        SessionPasswordStore(path)
                    self.assertEqual(raw, path.read_text(encoding="utf-8"))

    def test_decryption_failure_is_explicit_and_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            SessionPasswordStore(path).replace(["kept-secret"])
            with patch.object(SessionPasswordStore, "_unprotect", side_effect=OSError("secret: kept-secret")):
                with self.assertRaises(PasswordStoreError) as raised:
                    SessionPasswordStore(path)
            self.assertNotIn("kept-secret", str(raised.exception))

    def test_atomic_replace_failure_keeps_file_and_in_memory_library(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            store = SessionPasswordStore(path)
            store.replace(["existing-password"])
            before = path.read_bytes()
            with patch("password.session_store.os.replace", side_effect=OSError("secret new-password")):
                with self.assertRaises(PasswordStoreError) as raised:
                    store.replace(["new-password"])
            self.assertNotIn("new-password", str(raised.exception))
            self.assertEqual(["existing-password"], store.passwords())
            self.assertEqual(before, path.read_bytes())
            self.assertEqual([], list(path.parent.glob(".passwords-*.tmp")))
            self.assertEqual(["existing-password"], SessionPasswordStore(path).passwords())

    def test_encryption_failure_keeps_previous_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            store = SessionPasswordStore(path)
            store.replace(["safe-old"])
            before = path.read_bytes()
            with patch.object(SessionPasswordStore, "_protect", side_effect=OSError("secret safe-old")):
                with self.assertRaises(PasswordStoreError) as raised:
                    store.replace(["new-secret"])
            self.assertNotIn("safe-old", str(raised.exception))
            self.assertEqual(["safe-old"], store.passwords())
            self.assertEqual(before, path.read_bytes())
            self.assertEqual([], list(path.parent.glob(".passwords-*.tmp")))

    def test_verified_passwords_stay_session_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            store = SessionPasswordStore(path)
            store.replace(["saved"])
            store.add_verified("verified-in-session")
            self.assertEqual(1, len(store))
            self.assertEqual(2, len(store.candidates()))
            reloaded = SessionPasswordStore(path)
            self.assertEqual(["saved"], reloaded.passwords())
            self.assertEqual(0, len(reloaded))


if __name__ == "__main__":
    unittest.main()
