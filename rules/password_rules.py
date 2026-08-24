"""密码候选的基础规则。"""

import re

# 数字越小，表示候选密码的尝试优先级越高。
PASSWORD_PRIORITY = {
    "empty_folder_name": 1,
    "folder_name_part": 2,
}


def password_from_empty_folder(folder_name: str) -> str:
    """把空文件夹名称保留为一个高优先级密码候选。"""
    return folder_name.strip()


def split_folder_name(folder_name: str) -> list[str]:
    """按常见分隔符拆分文件夹名称，作为后续密码候选。"""
    parts = re.split(r"[\s._\-]+", folder_name.strip())
    return [part for part in parts if part]
