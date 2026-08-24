"""决定下一次使用哪个密码，不执行任何解压操作。"""

from pathlib import Path

from config.settings import Settings
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from password.models import PasswordCandidate
from password.scoring import PasswordScorer
from recovery.models import PasswordAttemptPlan


class PasswordRecoveryEngine:
    """连接解压状态和已排序密码候选。"""

    PASSWORD_STATUSES = {
        ExtractionStatus.PASSWORD_REQUIRED,
        ExtractionStatus.WRONG_PASSWORD,
    }

    def __init__(
        self,
        extraction_result: ExtractionResult,
        password_candidates: list[PasswordCandidate],
        archive_path: str | Path,
        max_attempts: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        active_settings = settings or Settings()
        max_attempts = (
            active_settings.max_password_attempts
            if max_attempts is None
            else max_attempts
        )

        if max_attempts < 0:
            raise ValueError("max_attempts 不能小于 0")

        # 评分器返回新列表，不删除或修改 Password Manager 的原始候选。
        ordered_candidates = PasswordScorer().sort_candidates(password_candidates)
        allowed_attempts = len(ordered_candidates)
        allowed_attempts = min(max_attempts, allowed_attempts)

        # 非密码状态不应产生密码尝试。
        if extraction_result.status not in self.PASSWORD_STATUSES:
            allowed_attempts = 0

        self.extraction_result = extraction_result
        self.plan = PasswordAttemptPlan(
            archive_path=Path(archive_path).expanduser(),
            password_candidates=ordered_candidates,
            current_index=0,
            max_attempts=allowed_attempts,
        )

    def next_password(self) -> str | None:
        """按现有顺序返回下一个密码；没有候选时返回 None。"""
        if self.plan.current_index >= self.plan.max_attempts:
            return None

        candidate = self.plan.password_candidates[self.plan.current_index]
        self.plan.current_index += 1
        return candidate.password
