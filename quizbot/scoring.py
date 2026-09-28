from dataclasses import dataclass

BASE_POINTS = {"easy": 10, "medium": 20, "hard": 30}
SPEED_BONUS_RATIO = 0.5  # 立刻作答最多再加基本分的 50%
STREAK_BONUS_STEP = 5
STREAK_BONUS_MAX = 25


@dataclass(frozen=True)
class ScoreResult:
    points: int
    base: int
    speed_bonus: int
    streak_bonus: int


def calculate_score(correct: bool, difficulty: str, elapsed: float, time_limit: float, streak: int) -> ScoreResult:
    """計算單題得分。streak 為「含本題」的連續答對題數。"""
    if not correct:
        return ScoreResult(0, 0, 0, 0)
    base = BASE_POINTS.get(difficulty, BASE_POINTS["medium"])
    remaining = min(max(time_limit - elapsed, 0.0), time_limit) / time_limit if time_limit > 0 else 0.0
    speed_bonus = int(base * SPEED_BONUS_RATIO * remaining + 0.5)  # 四捨五入（round() 是銀行家捨入）
    streak_bonus = min(max(streak - 1, 0) * STREAK_BONUS_STEP, STREAK_BONUS_MAX)
    return ScoreResult(base + speed_bonus + streak_bonus, base, speed_bonus, streak_bonus)
