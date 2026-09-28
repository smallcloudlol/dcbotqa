from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from quizbot.scoring import BASE_POINTS

MIN_OPTIONS = 2
MAX_OPTIONS = 5  # Discord 一列最多放 5 個按鈕


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    difficulty: str
    question: str
    options: Tuple[str, ...]
    answer: int  # 正確選項的索引（從 0 開始）
    explanation: str = ""


def parse_question(item: Dict[str, Any]) -> Question:
    question = Question(
        id=str(item["id"]),
        category=str(item["category"]).strip(),
        difficulty=str(item.get("difficulty", "medium")),
        question=str(item["question"]).strip(),
        options=tuple(str(option) for option in item["options"]),
        answer=int(item["answer"]),
        explanation=str(item.get("explanation", "")),
    )
    if not question.question or not question.category:
        raise ValueError(f"題目 {question.id}：question 與 category 不可為空")
    if not MIN_OPTIONS <= len(question.options) <= MAX_OPTIONS:
        raise ValueError(f"題目 {question.id}：選項數量需介於 {MIN_OPTIONS}～{MAX_OPTIONS}")
    if not 0 <= question.answer < len(question.options):
        raise ValueError(f"題目 {question.id}：answer 需為選項索引 0～{len(question.options) - 1}")
    if question.difficulty not in BASE_POINTS:
        raise ValueError(f"題目 {question.id}：difficulty 需為 {' / '.join(BASE_POINTS)}")
    return question


class QuestionBank:
    def __init__(self, path: str):
        self.path = path
        self.questions: List[Question] = []
        self.reload()

    def reload(self) -> int:
        """重新讀取題庫。檔案有誤時會拋出例外，並保留原本的題目。"""
        with open(self.path, encoding="utf-8") as file:
            raw = json.load(file)
        questions = [parse_question(item) for item in raw]
        if not questions:
            raise ValueError("題庫是空的")
        seen = set()
        for question in questions:
            if question.id in seen:
                raise ValueError(f"題目 id 重複：{question.id}")
            seen.add(question.id)
        self.questions = questions
        return len(questions)

    def categories(self) -> List[str]:
        return list(dict.fromkeys(question.category for question in self.questions))

    def random(self, category: Optional[str] = None, exclude: Iterable[str] = ()) -> Optional[Question]:
        """隨機抽一題，盡量避開 exclude 中最近答過的題目。"""
        pool = [q for q in self.questions if category is None or q.category == category]
        excluded = set(exclude)
        candidates = [q for q in pool if q.id not in excluded] or pool
        return random.choice(candidates) if candidates else None
