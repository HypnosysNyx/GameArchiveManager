"""按有限候选顺序执行密码重试。"""

from dataclasses import replace
from pathlib import Path

from config.settings import Settings
from execution.models import ExtractionPlan
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from extractor.seven_zip import SevenZipExtractor
from recovery.password_recovery import PasswordRecoveryEngine


class PasswordRetryExecutor:
    """连接 Recovery Engine 与 7-Zip，不保存或评分密码。"""

    DEFAULT_MAX_PASSWORD_ATTEMPTS = 20
    ABSOLUTE_MAX_PASSWORD_ATTEMPTS = 100

    def __init__(
        self,
        plan: ExtractionPlan,
        recovery_engine: PasswordRecoveryEngine,
        extractor: SevenZipExtractor,
        max_password_attempts: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        active_settings = settings or Settings()
        max_password_attempts = (
            active_settings.max_password_attempts
            if max_password_attempts is None
            else max_password_attempts
        )

        if max_password_attempts < 0:
            raise ValueError("max_password_attempts 不能小于 0")
        if max_password_attempts > self.ABSOLUTE_MAX_PASSWORD_ATTEMPTS:
            raise ValueError(
                f"max_password_attempts 不能超过 "
                f"{self.ABSOLUTE_MAX_PASSWORD_ATTEMPTS}"
            )

        self.plan = plan
        self.recovery_engine = recovery_engine
        self.extractor = extractor
        self.max_password_attempts = max_password_attempts

        # 保存每次失败原因和最终结果，但不保存对应的密码。
        self.attempt_results: list[ExtractionResult] = []

    def execute(self) -> ExtractionResult:
        """先正常解压；需要密码时再按候选顺序有限重试。"""
        self.attempt_results = []
        first_result = self.extractor.extract(self.plan)
        self.attempt_results.append(first_result)

        if first_result.status is not ExtractionStatus.PASSWORD_REQUIRED:
            return first_result

        last_result = first_result
        password_attempts = 0

        while password_attempts < self.max_password_attempts:
            password = self.recovery_engine.next_password()
            if password is None:
                break

            password_attempts += 1
            retry_plan = replace(
                self.plan,
                output_path=self._retry_output_path(password_attempts),
                requires_password=False,
            )
            last_result = self.extractor.extract(retry_plan, password=password)
            self.attempt_results.append(last_result)

            if last_result.status is ExtractionStatus.SUCCESS:
                return last_result
            if last_result.status is not ExtractionStatus.WRONG_PASSWORD:
                return last_result

        return last_result

    def _retry_output_path(self, attempt_number: int) -> Path | None:
        """为重试选择未覆盖首次结果的独立建议目录。"""
        output = self.plan.output_path
        if output is None or not output.exists():
            return output

        return output.parent / f"{output.name}_password_attempt_{attempt_number}"
