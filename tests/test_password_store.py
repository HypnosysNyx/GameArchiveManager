import tempfile
import unittest
from pathlib import Path

from password.session_store import SessionPasswordStore


class PasswordStoreTests(unittest.TestCase):
    def test_saved_passwords_are_available_to_a_new_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passwords.json"
            SessionPasswordStore(path).replace(["fixture-password", "fixture-password"])
            reloaded = SessionPasswordStore(path)
            self.assertEqual(["fixture-password"], reloaded.passwords())
            self.assertEqual(1, len(reloaded.candidates()))


if __name__ == "__main__":
    unittest.main()
