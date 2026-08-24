"""基于 Python 标准库 logging 的任务日志接口。"""

import logging
import re
from pathlib import Path


class GameLogger:
    """为单个任务创建日志文件，并统一执行基础脱敏。"""

    MAX_MESSAGE_LENGTH = 500

    def __init__(
        self,
        task_id: str,
        log_directory: str | Path = "logs",
    ) -> None:
        safe_task_id = re.sub(r"[^\w.-]", "_", str(task_id)) or "unknown"
        self.log_directory = Path(log_directory).expanduser()
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_directory / f"task_{safe_task_id}.log"

        # 每个实例使用独立 logger，避免重复添加处理器或传播到根 logger。
        logger_name = f"GameArchiveManager.task.{safe_task_id}.{id(self)}"
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        self._handler = logging.FileHandler(
            self.log_path,
            mode="a",
            encoding="utf-8",
        )
        self._handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self._logger.addHandler(self._handler)

    def info(self, message: object) -> None:
        """记录普通信息，并在写入前脱敏。"""
        self._logger.info(self._sanitize(message))

    def warning(self, message: object) -> None:
        """记录警告信息，并在写入前脱敏。"""
        self._logger.warning(self._sanitize(message))

    def error(self, message: object) -> None:
        """记录简短错误摘要，不保存完整外部工具输出。"""
        self._logger.error(self._sanitize(message))

    def task_started(self, task_path: str | Path) -> None:
        self.info(f"任务开始: {task_path}")

    def analysis_started(self) -> None:
        self.info("分析开始")

    def archives_found(self, count: int) -> None:
        self.info(f"发现压缩包: {count} 个")

    def extraction_started(self, archive_path: str | Path) -> None:
        self.info(f"解压开始: {archive_path}")

    def extraction_succeeded(
        self,
        archive_path: str | Path,
        output_path: str | Path | None = None,
    ) -> None:
        message = f"解压成功: {archive_path}"
        if output_path is not None:
            message += f"，输出目录: {output_path}"
        self.info(message)

    def extraction_failed(
        self,
        archive_path: str | Path,
        reason: object = "未知原因",
    ) -> None:
        self.error(f"解压失败: {archive_path}，原因摘要: {reason}")

    def password_recovery_started(
        self, archive_path: str | Path, candidate_count: int
    ) -> None:
        self.info(
            f"密码恢复开始: {archive_path}，候选数量: {candidate_count}"
        )

    def password_recovery_finished(
        self, success: bool, attempt_count: int
    ) -> None:
        result = "成功" if success else "失败"
        self.info(f"密码恢复结果: {result}，尝试次数: {attempt_count}")

    def close(self) -> None:
        """刷新并关闭日志文件，便于测试和应用安全释放资源。"""
        if self._handler is None:
            return
        self._handler.flush()
        self._handler.close()
        self._logger.removeHandler(self._handler)
        self._handler = None

    def __enter__(self) -> "GameLogger":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @classmethod
    def _sanitize(cls, message: object) -> str:
        """遮盖常见密码表达，并截断可能包含敏感内容的长输出。"""
        safe = " ".join(str(message).split())
        safe = re.sub(
            r"(?i)\b(password|pwd)\s*[:=]\s*\S+",
            r"\1=[REDACTED]",
            safe,
        )
        safe = re.sub(
            r"(?i)\bpassword\s+(?:is\s+)?\S+",
            "password=[REDACTED]",
            safe,
        )
        safe = re.sub(r"密码\s*[:：=]\s*\S+", "密码=[已隐藏]", safe)
        safe = re.sub(r"(?i)(?<!\w)-p\S+", "-p[REDACTED]", safe)
        if len(safe) > cls.MAX_MESSAGE_LENGTH:
            safe = safe[: cls.MAX_MESSAGE_LENGTH] + "..."
        return safe
