"""密码候选的内存管理器。"""

from pathlib import Path

from password.models import PasswordCandidate, PasswordSource, PlatformHint


class PasswordManager:
    """保存、添加并排序密码候选，不测试密码是否正确。"""

    def __init__(self) -> None:
        self.candidates: list[PasswordCandidate] = []

    def add_user_password(
        self, password: str, priority: int = 0
    ) -> PasswordCandidate:
        """添加用户直接输入的密码，默认具有最高优先级。"""
        candidate = PasswordCandidate(
            password=password,
            source=PasswordSource.USER_INPUT,
            priority=priority,
        )
        self.candidates.append(candidate)
        return candidate

    def add_folder_name_candidate(
        self,
        folder_path: str | Path,
        priority: int = 10,
        platform_hint: PlatformHint | str = PlatformHint.UNKNOWN,
    ) -> PasswordCandidate:
        """把文件夹名称及其原始路径添加为密码候选。"""
        path = Path(folder_path).expanduser()

        # 只有调用者提供了完整路径时才记录，避免把单独名称误认为真实路径。
        source_path = path.resolve() if path.is_absolute() else None
        password = path.name if source_path is not None else str(folder_path)

        candidate = PasswordCandidate(
            password=password,
            source=PasswordSource.FOLDER_NAME,
            source_path=source_path,
            platform_hint=PlatformHint(platform_hint),
            priority=priority,
        )
        self.candidates.append(candidate)
        return candidate

    def get_candidates_by_priority(self) -> list[PasswordCandidate]:
        """按优先级返回新列表；数字越小，候选越靠前。"""
        return sorted(self.candidates, key=lambda candidate: candidate.priority)
