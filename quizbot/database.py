from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    username    TEXT    NOT NULL,
    score       INTEGER NOT NULL DEFAULT 0,
    answered    INTEGER NOT NULL DEFAULT 0,
    correct     INTEGER NOT NULL DEFAULT 0,
    streak      INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- 每一次作答的紀錄，供使用者測試與成效分析使用
CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    question_id TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    mode        TEXT    NOT NULL,          -- quiz / challenge
    chosen      INTEGER,                   -- NULL 代表逾時未作答
    correct     INTEGER NOT NULL,
    elapsed     REAL,
    points      INTEGER NOT NULL,
    answered_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_score ON users (guild_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_answers_user ON answers (guild_id, user_id);
"""


@dataclass
class UserStats:
    user_id: int
    username: str
    score: int
    answered: int
    correct: int
    streak: int
    best_streak: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.answered if self.answered else 0.0


@dataclass
class CategoryStats:
    category: str
    answered: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.answered if self.answered else 0.0


USER_COLUMNS = "user_id, username, score, answered, correct, streak, best_streak"


class Database:
    def __init__(self, path: str):
        if path != ":memory:" and os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def get_user(self, guild_id: int, user_id: int) -> Optional[UserStats]:
        row = self._conn.execute(
            f"SELECT {USER_COLUMNS} FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        return UserStats(**dict(row)) if row else None

    def record_answer(
        self,
        *,
        guild_id: int,
        user_id: int,
        username: str,
        question_id: str,
        category: str,
        mode: str,
        chosen: Optional[int],
        correct: bool,
        elapsed: Optional[float],
        points: int,
    ) -> UserStats:
        with self._conn:
            self._conn.execute(
                """INSERT INTO users (guild_id, user_id, username) VALUES (?, ?, ?)
                   ON CONFLICT (guild_id, user_id) DO UPDATE SET username = excluded.username""",
                (guild_id, user_id, username),
            )
            # SQLite 的 UPDATE 右側一律讀取舊值，所以 best_streak 會用到更新前的 streak
            self._conn.execute(
                """UPDATE users SET
                       score = score + :points,
                       answered = answered + 1,
                       correct = correct + :correct,
                       streak = CASE WHEN :correct THEN streak + 1 ELSE 0 END,
                       best_streak = MAX(best_streak, CASE WHEN :correct THEN streak + 1 ELSE 0 END)
                   WHERE guild_id = :guild_id AND user_id = :user_id""",
                {"points": points, "correct": int(correct), "guild_id": guild_id, "user_id": user_id},
            )
            self._conn.execute(
                """INSERT INTO answers (guild_id, user_id, question_id, category, mode, chosen, correct, elapsed, points)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (guild_id, user_id, question_id, category, mode, chosen, int(correct), elapsed, points),
            )
        stats = self.get_user(guild_id, user_id)
        assert stats is not None
        return stats

    def rank(self, guild_id: int, user_id: int) -> Optional[int]:
        row = self._conn.execute(
            "SELECT score FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        ).fetchone()
        if row is None:
            return None
        higher = self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE guild_id = ? AND score > ?", (guild_id, row["score"])
        ).fetchone()[0]
        return higher + 1

    def leaderboard(self, guild_id: int, limit: int = 10) -> List[UserStats]:
        rows = self._conn.execute(
            f"""SELECT {USER_COLUMNS} FROM users WHERE guild_id = ?
                ORDER BY score DESC, correct DESC, answered ASC LIMIT ?""",
            (guild_id, limit),
        ).fetchall()
        return [UserStats(**dict(row)) for row in rows]

    def category_stats(self, guild_id: int, user_id: int) -> List[CategoryStats]:
        rows = self._conn.execute(
            """SELECT category, COUNT(*) AS answered, SUM(correct) AS correct FROM answers
               WHERE guild_id = ? AND user_id = ? GROUP BY category ORDER BY answered DESC""",
            (guild_id, user_id),
        ).fetchall()
        return [CategoryStats(**dict(row)) for row in rows]

    def recent_question_ids(self, guild_id: int, user_id: int, limit: int) -> List[str]:
        rows = self._conn.execute(
            "SELECT question_id FROM answers WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, user_id, limit),
        ).fetchall()
        return [row["question_id"] for row in rows]

    def export_answers(self, guild_id: int) -> List[sqlite3.Row]:
        return self._conn.execute(
            """SELECT a.id, a.answered_at, a.user_id, COALESCE(u.username, '') AS username, a.mode,
                      a.question_id, a.category, a.chosen, a.correct, a.elapsed, a.points
               FROM answers a
               LEFT JOIN users u ON u.guild_id = a.guild_id AND u.user_id = a.user_id
               WHERE a.guild_id = ? ORDER BY a.id""",
            (guild_id,),
        ).fetchall()
