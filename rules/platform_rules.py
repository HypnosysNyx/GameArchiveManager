"""平台内容名称判断规则。"""

import re


ANDROID_NAME_MARKERS = ("android", "安卓")

# AZ 是发布资源使用的平台标签。它必须是独立 ASCII token；下划线、
# 连字符、括号或中文可以作为边界，普通英文单词中的 az 不能触发跳过。
AZ_TOKEN_PATTERN = re.compile(r"(?<![a-z0-9])az(?![a-z0-9])", re.IGNORECASE)


def is_android_name(name: str) -> bool:
    """保持既有 Android/安卓 名称包含语义。"""
    normalized_name = name.casefold()
    return any(marker in normalized_name for marker in ANDROID_NAME_MARKERS)


def is_az_name(name: str) -> bool:
    """只接受明确的 AZ token，不接受英文单词内部的弱子串。"""
    return AZ_TOKEN_PATTERN.search(name) is not None


def is_android_or_az(name: str) -> bool:
    """判断一个内容相关名称是否包含受支持的平台标签。"""
    return is_android_name(name) or is_az_name(name)
