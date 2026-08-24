"""真实验证密码分析与单包解压模块的连接流程。"""

import sys
from pathlib import Path

# 直接运行 tests 下的脚本时，将项目根目录加入模块搜索路径。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution.strategy import ExecutionStrategy
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from extractor.seven_zip import SevenZipExtractor
from recovery.password_executor import PasswordRetryExecutor
from recovery.password_recovery import PasswordRecoveryEngine
from task.models import Task
from task.task_analyzer import AnalysisStatus, TaskAnalyzer


TEST_TASK_PATH = Path(r"C:\Users\<redacted>\Documents\GAM_Test")
MAX_PASSWORD_ATTEMPTS = 20


def print_password_candidates(candidates: list) -> None:
    """打印 TaskAnalyzer 收集到的密码候选。"""
    print(f"密码候选列表（{len(candidates)}）:")
    if not candidates:
        print("  无")
        return

    for index, candidate in enumerate(candidates, start=1):
        print(f"  {index}. 密码: {candidate.password}")
        print(f"     来源: {candidate.source.value}")
        print(f"     来源路径: {candidate.source_path or '无'}")
        print(f"     平台提示: {candidate.platform_hint.value}")


def print_attempt_results(results: list[ExtractionResult]) -> None:
    """打印首次解压和每次密码重试的完整结果。"""
    print(f"每次尝试结果（{len(results)}）:")
    for index, result in enumerate(results):
        label = "首次普通解压" if index == 0 else f"密码尝试 {index}"
        print(f"  [{label}]")
        print(f"    状态: {result.status.value}")
        print(f"    是否成功: {result.success}")
        print(f"    消息: {result.message}")
        print(f"    错误: {result.error or '无'}")
        print(f"    使用工具: {result.tool_used.value if result.tool_used else '无'}")
        print(f"    输出目录: {result.output_path or '无'}")


def main() -> None:
    print("GameArchiveManager 真实密码流程测试")
    print(f"任务目录: {TEST_TASK_PATH}")

    if not TEST_TASK_PATH.is_dir():
        print("测试失败: 任务目录不存在或不是文件夹")
        return

    task = Task(TEST_TASK_PATH)
    analysis = TaskAnalyzer().analyze(task)
    if analysis.analysis_status is AnalysisStatus.FAILED:
        print(f"分析失败: {analysis.error_message}")
        return

    print(f"发现压缩包数量: {len(analysis.archive_results)}")
    print_password_candidates(analysis.password_candidates)

    if not analysis.archive_results:
        print("没有发现可测试的 ZIP、RAR 或 7Z 压缩包")
        return

    strategy = ExecutionStrategy()
    extractor = SevenZipExtractor()

    for archive_number, archive_info in enumerate(
        analysis.archive_results, start=1
    ):
        print("\n" + "=" * 60)
        print(f"压缩包编号: {archive_number}")
        print(f"压缩包路径: {archive_info.file_path}")
        print(f"检测格式: {archive_info.real_format}")
        print(f"原扩展名: {archive_info.extension or '无'}")
        print(f"是否伪装: {archive_info.is_fake_extension}")

        plan = strategy.create_plan(archive_info)
        if not plan.can_execute:
            print(f"无法创建可执行计划: {plan.message}")
            continue

        # Recovery Engine 需要密码相关状态来启用候选序列。
        # PasswordRetryExecutor 仍会先执行一次真实的普通解压。
        password_state = ExtractionResult(
            success=False,
            message="等待首次解压确认是否需要密码",
            status=ExtractionStatus.PASSWORD_REQUIRED,
        )
        recovery_engine = PasswordRecoveryEngine(
            extraction_result=password_state,
            password_candidates=analysis.password_candidates,
            archive_path=plan.archive_path,
            max_attempts=min(
                len(analysis.password_candidates), MAX_PASSWORD_ATTEMPTS
            ),
        )
        executor = PasswordRetryExecutor(
            plan=plan,
            recovery_engine=recovery_engine,
            extractor=extractor,
            max_password_attempts=MAX_PASSWORD_ATTEMPTS,
        )
        final_result = executor.execute()

        print_attempt_results(executor.attempt_results)
        print(f"最终状态: {final_result.status.value}")
        print(f"解压输出目录: {final_result.output_path or '无'}")

    print("\n测试结束。脚本未删除任何测试目录或输出文件。")


if __name__ == "__main__":
    main()
