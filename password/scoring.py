"""密码候选评分和排序规则。"""

from password.models import PasswordCandidate, PasswordSource, PlatformHint


class PasswordScorer:
    """计算临时分数并按高分优先排序，不修改候选对象。"""

    COMMON_PASSWORD_FEATURES = ("123456", "password", "game", "steam")
    UNLIKELY_PASSWORD_NAMES = {"readme", "android_game", "game"}

    def score(self, candidate: PasswordCandidate) -> int:
        """根据候选来源、内容和平台提示计算分数。"""
        score = 0

        # 来源规则。
        if candidate.source is PasswordSource.USER_INPUT:
            score += 100
        elif candidate.source is PasswordSource.SESSION_MEMORY:
            score += 90
        elif candidate.source is PasswordSource.HISTORY:
            successful_uses = max(candidate.success_count, 0)
            score += min(successful_uses * 5, 50)
        elif candidate.source is PasswordSource.FOLDER_NAME:
            score += 30

        normalized_password = candidate.password.strip().casefold()

        # 内容规则。
        if normalized_password.isdigit() and 6 <= len(normalized_password) <= 12:
            score += 20

        for feature in self.COMMON_PASSWORD_FEATURES:
            if feature in normalized_password:
                score += 5

        # 明显像说明文件或平台目录的完整名称降低优先级，但不删除候选。
        if normalized_password in self.UNLIKELY_PASSWORD_NAMES:
            score -= 30

        if candidate.platform_hint is PlatformHint.ANDROID:
            score -= 50

        return score

    def sort_candidates(
        self, candidates: list[PasswordCandidate]
    ) -> list[PasswordCandidate]:
        """返回按评分从高到低排列的新列表。"""
        return sorted(candidates, key=self.score, reverse=True)
