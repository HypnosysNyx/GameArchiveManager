"""Local, user-scoped storage for verified archive passwords."""

import base64
import ctypes
import json
from ctypes import wintypes
from pathlib import Path

from application.runtime_paths import user_data_directory
from password.models import PasswordCandidate, PasswordSource


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class SessionPasswordStore:
    """Keep session-verified passwords separate from the local password library."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else user_data_directory() / "passwords.json"
        self._saved_passwords = self._load()
        self._verified_passwords: list[str] = []

    def add_verified(self, password: str) -> None:
        if password and password not in self._verified_passwords:
            self._verified_passwords.append(password)

    def passwords(self) -> list[str]:
        """Return a copy for the local settings editor."""
        return self._saved_passwords.copy()

    def replace(self, passwords: list[str]) -> None:
        """Replace the library, discarding blank and duplicate entries."""
        self._saved_passwords = list(
            dict.fromkeys(password for password in passwords if password)
        )
        self.save()

    def save(self) -> None:
        protected = self._protect(json.dumps(self._saved_passwords).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"version": 1, "protected_passwords": base64.b64encode(protected).decode("ascii")}),
            encoding="utf-8",
        )

    def _load(self) -> list[str]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            encrypted = base64.b64decode(data["protected_passwords"], validate=True)
            passwords = json.loads(self._unprotect(encrypted).decode("utf-8"))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return []
        return list(dict.fromkeys(password for password in passwords if isinstance(password, str) and password))

    @staticmethod
    def _protect(value: bytes) -> bytes:
        return SessionPasswordStore._crypt(value, protect=True)

    @staticmethod
    def _unprotect(value: bytes) -> bytes:
        return SessionPasswordStore._crypt(value, protect=False)

    @staticmethod
    def _crypt(value: bytes, protect: bool) -> bytes:
        if not value:
            return b""
        try:
            crypt32 = ctypes.windll.crypt32
            local_free = ctypes.windll.kernel32.LocalFree
        except AttributeError as error:
            raise OSError("本机密码库需要 Windows 数据保护 API") from error
        source = ctypes.create_string_buffer(value)
        input_blob = _DataBlob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
        output_blob = _DataBlob()
        if protect:
            succeeded = crypt32.CryptProtectData(
                ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
            )
        else:
            succeeded = crypt32.CryptUnprotectData(
                ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
            )
        if not succeeded:
            raise OSError("无法保护本机密码库")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            local_free(output_blob.pbData)

    def candidates(self) -> list[PasswordCandidate]:
        session_candidates = [
            PasswordCandidate(
                password=password,
                source=PasswordSource.SESSION_MEMORY,
                priority=1,
            )
            for password in self._verified_passwords
        ]
        session_passwords = set(self._verified_passwords)
        return session_candidates + [
            PasswordCandidate(
                password=password,
                source=PasswordSource.USER_INPUT,
                priority=1,
            )
            for password in self._saved_passwords
            if password not in session_passwords
        ]

    def __len__(self) -> int:
        return len(self._verified_passwords)
