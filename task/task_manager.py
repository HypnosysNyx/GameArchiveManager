"""Task Manager 的基础控制结构。"""

from pathlib import Path

from task.models import Task, TaskStatus


class TaskManager:
    """创建、保存和管理当前程序运行期间的任务。"""

    def __init__(self) -> None:
        # 当前只保存在内存中，不使用数据库或配置文件。
        self.tasks: list[Task] = []

    def create_task(self, task_path: str | Path) -> Task:
        """根据用户输入的文件夹路径创建并保存任务。"""
        task = Task(task_path=Path(task_path))
        self.tasks.append(task)
        return task

    def update_task_status(
        self, task_id: str, status: TaskStatus | str
    ) -> Task:
        """更新指定任务的状态，并返回更新后的任务。"""
        task = self._find_task(task_id)
        task.status = TaskStatus(status)
        return task

    def get_tasks(self) -> list[Task]:
        """返回任务列表副本，避免外部直接修改内部列表。"""
        return self.tasks.copy()

    def scan_task(self, task_id: str) -> None:
        """预留扫描流程接口。"""
        self._find_task(task_id)
        raise NotImplementedError("扫描流程尚未接入")

    def confirm_task(self, task_id: str) -> None:
        """预留用户确认流程接口。"""
        self._find_task(task_id)
        raise NotImplementedError("确认流程尚未接入")

    def execute_task(self, task_id: str) -> None:
        """预留任务执行流程接口。"""
        self._find_task(task_id)
        raise NotImplementedError("执行流程尚未接入")

    def _find_task(self, task_id: str) -> Task:
        """根据唯一编号查找任务。"""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f"未找到任务: {task_id}")
