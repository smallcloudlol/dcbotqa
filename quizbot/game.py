from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from quizbot.database import Database, UserStats
from quizbot.questions import Question
from quizbot.scoring import ScoreResult, calculate_score


@dataclass
class Outcome:
    chosen: Optional[int]  # None 代表逾時
    correct: bool
    elapsed: float
    score: ScoreResult
    stats: UserStats  # 作答後的最新統計
    rank: int


def settle_answer(
    db: Database,
    *,
    guild_id: int,
    user_id: int,
    username: str,
    question: Question,
    chosen: Optional[int],
    elapsed: float,
    time_limit: float,
    mode: str,
) -> Outcome:
    """判定對錯、計分並寫入資料庫。"""
    elapsed = min(max(elapsed, 0.0), float(time_limit))
    correct = chosen is not None and chosen == question.answer

    before = db.get_user(guild_id, user_id)
    if correct:
        streak_after = (before.streak if before else 0) + 1
    else:
        streak_after = 0
    score = calculate_score(correct, question.difficulty, elapsed, time_limit, streak_after)

    stats = db.record_answer(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        question_id=question.id,
        category=question.category,
        mode=mode,
        chosen=chosen,
        correct=correct,
        elapsed=elapsed if chosen is not None else None,
        points=score.points,
    )
    rank = db.rank(guild_id, user_id) or 1
    return Outcome(chosen, correct, elapsed, score, stats, rank)
