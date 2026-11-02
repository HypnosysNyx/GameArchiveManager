"""Local, user-scoped storage for verified archive passwords."""

import base64
import binascii
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

from application.runtime_paths import user_data_directory
from password.models import PasswordCandidate, PasswordSource


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class PasswordStoreError(OSError):
    """A sanitized error safe to display without exposing stored passwords."""


class SessionPasswordStore:
    """Keep session-verified passwords separate from the local password library."""

    def __init__(self, path: str | Path | None = None, *, persist_verified: bool = False) -> None:
        self.path = Path(path) if path is not None else user_data_directory() / "passwords.json"
        self._saved_passwords = self._load()
        self._verified_passwords: list[str] = []
        self.persist_verified = bool(persist_verified)
        self.last_persistence_error: str | None = None

    def add_verified(self, password: str, *, persist: bool | None = None) -> None:
        """Remember a proven password in-session; optionally persist it safely."""
        if not password:
            return
        if password not in self._verified_passwords:
            self._verified_passwords.append(password)
        should_persist = self.persist_verified if persist is None else persist
        if not should_persist or password in self._saved_passwords:
            return
        try:
            # Re-read before append so a recently edited local library is not
            # overwritten by a stale long-running extraction session.
            current = SessionPasswordStore(self.path)
            saved = current.passwords()
            if password not in saved:
                current.replace(saved + [password])
            self._saved_passwords = current.passwords()
            self.last_persistence_error = None
        except PasswordStoreError as error:
            # A failed optional save must not turn a successful extraction
            # into a failed job or lose verified in-session reuse.
            self.last_persistence_error = str(error)

    def verified_passwords(self) -> list[str]:
        """Copy only session-verified values for reuse across GUI tasks."""
        return self._verified_passwords.copy()

    def passwords(self) -> list[str]:
        """Return a copy for the local settings editor."""
        return self._saved_passwords.copy()

    def replace(self, passwords: list[str]) -> None:
        """Persist a new library, updating memory only after the write succeeds."""
        updated = list(dict.fromkeys(password for password in passwords if isinstance(password, str) and password))
        self._write(updated)
        self._saved_passwords = updated

    def save(self) -> None:
        """Persist the current library without changing the verified session list."""
        self._write(self._saved_passwords)

    def _write(self, passwords: list[str]) -> None:
        """Write encrypted bytes to a sibling temp file, then atomically replace."""
        if sys.platform.startswith("linux"):
            self._write_linux(passwords)
            return
        try:
            protected = self._protect(json.dumps(passwords, ensure_ascii=False).encode("utf-8"))
        except OSError as error:
            raise PasswordStoreError("无法加密本机密码库；未保存修改。") from error

        data = json.dumps(
            {"version": 1, "protected_passwords": base64.b64encode(protected).decode("ascii")},
            ensure_ascii=False,
        )
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # The temporary file contains only DPAPI-protected data, never passwords in plaintext.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=".passwords-",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise PasswordStoreError("无法安全保存本机密码库；旧文件未被主动覆盖。") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    # Failed cleanup only leaves an encrypted temporary file.
                    pass

    def _load(self) -> list[str]:
        if sys.platform.startswith("linux"):
            return self._load_linux()
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError) as error:
            raise PasswordStoreError("无法读取本机密码库，请检查文件权限或存储状态。") from error

        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
                raise ValueError("unsupported password library version")
            encoded = data.get("protected_passwords")
            if not isinstance(encoded, str):
                raise ValueError("missing encrypted password payload")
            encrypted = base64.b64decode(encoded, validate=True)
            passwords = json.loads(self._unprotect(encrypted).decode("utf-8"))
            if not isinstance(passwords, list) or any(not isinstance(value, str) for value in passwords):
                raise ValueError("invalid password library payload")
        except (OSError, ValueError, TypeError, UnicodeError, binascii.Error) as error:
            raise PasswordStoreError(
                "本机密码库文件损坏，或无法由当前 Windows 用户解密；不会把它当作空密码库。"
            ) from error

        return list(dict.fromkeys(password for password in passwords if password))

    def _secret_command(self, action: str, value: str | None = None):
        """Use one Secret Service item per library; secrets travel only via pipes."""
        executable = shutil.which("secret-tool")
        if not executable or Path(executable).suffix.lower() == ".exe":
            raise PasswordStoreError("Linux 密码库需要 secret-tool 和已解锁的 Secret Service；未保存修改。")
        identity = hashlib.sha256(os.fsencode(self.path.expanduser().resolve())).hexdigest()
        command = [executable, action]
        if action == "store":
            command.append("--label=GameArchiveManager password library")
        command.extend(["application", "GameArchiveManager", "library", identity])
        try:
            return subprocess.run(
                command, input=value if value is not None else "",
                capture_output=True, text=True, encoding="utf-8",
                check=False, timeout=15,
            )
        except (OSError, UnicodeError, subprocess.SubprocessError):
            # Subprocess exceptions may carry stdin/stdout; never chain them.
            raise PasswordStoreError("无法访问 Linux Secret Service；密码库未读取或保存。") from None

    def _linux_marker_exists(self) -> bool:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        except (OSError, UnicodeError):
            raise PasswordStoreError("无法读取 Linux 密码库标记。") from None
        try:
            if json.loads(raw) != {"version": 1, "backend": "secret-service"}:
                raise ValueError()
        except (ValueError, TypeError):
            raise PasswordStoreError("Linux 密码库标记无效；不会覆盖或迁移现有密码文件。") from None
        return True

    def _load_linux(self) -> list[str]:
        exists = self._linux_marker_exists()
        # A fresh install can run without a desktop keyring. Existing data must
        # never silently become an empty editable library when access is lost.
        if not exists and not shutil.which("secret-tool"):
            return []
        try:
            result = self._secret_command("lookup")
        except PasswordStoreError:
            if exists:
                raise
            return []
        if not exists and result.returncode != 0:
            # An unavailable/locked desktop keyring must not block first boot.
            # Persistence still requires a successful secure backend write.
            return []
        if result.returncode != 0 or not result.stdout:
            raise PasswordStoreError("Linux 密码库不可用、已锁定或条目丢失；不会当作空库。")
        try:
            values = json.loads(result.stdout)
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError()
        except (ValueError, TypeError):
            raise PasswordStoreError("Linux Secret Service 密码库数据无效。") from None
        return list(dict.fromkeys(value for value in values if value))

    def _write_linux(self, passwords: list[str]) -> None:
        payload = json.dumps(passwords, ensure_ascii=False)
        # secret-tool's stdin reader has an 8192-byte limit. Reject before any
        # mutation rather than letting a truncated JSON library be stored.
        if len(payload.encode("utf-8")) >= 8192:
            raise PasswordStoreError("Linux 密码库超过 secret-tool 的单条安全传输容量；未保存修改。")
        # Validate any existing marker before contacting the keyring. A marker
        # contains no credentials and also guards against missing keyring items.
        exists = self._linux_marker_exists()
        if exists:
            self._load_linux()
        # Do not create any file when the native client is unavailable.
        if not shutil.which("secret-tool"):
            raise PasswordStoreError("Linux 密码库需要 secret-tool 和已解锁的 Secret Service；未保存修改。")
        # Commit the secret first: a failed first store must not leave a marker
        # that would make the next boot fail closed on a nonexistent item.
        # If marker creation fails afterwards, retain the secure item; lookup
        # without a marker recovers it on the next boot. Never clear user data.
        result = self._secret_command("store", payload)
        if result.returncode != 0:
            raise PasswordStoreError("Linux Secret Service 拒绝保存；请检查密钥环是否已解锁。")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not exists:
                # Exclusive creation preserves foreign files.
                with self.path.open("x", encoding="utf-8") as marker:
                    marker.write(json.dumps({"version": 1, "backend": "secret-service"}))
                    marker.flush()
                    os.fsync(marker.fileno())
        except OSError:
            raise PasswordStoreError("密码已写入 Linux Secret Service，但无法保存本机标记；请检查文件权限。") from None

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

    def candidates(self, *, include_saved: bool = True) -> list[PasswordCandidate]:
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
            for password in (self._saved_passwords if include_saved else [])
            if password not in session_passwords
        ]

    def __len__(self) -> int:
        return len(self._verified_passwords)
