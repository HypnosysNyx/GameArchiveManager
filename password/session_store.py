"""Process-memory-only storage for passwords that actually succeeded."""

from password.models import PasswordCandidate, PasswordSource


class SessionPasswordStore:
    """Keep verified passwords in memory; never serialize or log them."""

    def __init__(self) -> None:
        self._verified_passwords: list[str] = []

    def add_verified(self, password: str) -> None:
        if password and password not in self._verified_passwords:
            self._verified_passwords.append(password)

    def candidates(self) -> list[PasswordCandidate]:
        return [
            PasswordCandidate(
                password=password,
                source=PasswordSource.SESSION_MEMORY,
                priority=1,
            )
            for password in self._verified_passwords
        ]

    def __len__(self) -> int:
        return len(self._verified_passwords)
