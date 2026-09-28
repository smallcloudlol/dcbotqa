"""問卷分析：讀取 Google 表單等工具匯出的 CSV，計算各構面的平均數、標準差與 Cronbach's α。

題目欄位標題需以題號開頭，例如「A1. 我覺得用 Discord Bot 答題很新穎有趣」：
    A = 接受程度、B = 互動體驗、C = 使用意願
其餘欄位（時間戳記、基本資料、開放式問題）會自動略過。

用法：
    python tools/analyze_survey.py 問卷回覆.csv -o 問卷分析報告.md
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from typing import Dict, List, Optional, Sequence, Tuple

DIMENSIONS = {"A": "接受程度", "B": "互動體驗", "C": "使用意願"}
LIKERT_TEXT = {"非常不同意": 1, "不同意": 2, "普通": 3, "沒意見": 3, "同意": 4, "非常同意": 5}
ITEM_HEADER = re.compile(r"^\s*([A-Za-z])(\d+)(?:\s*[.．、:：]\s*|\s+|$)(.*)$")
LIKERT_NUMBER = re.compile(r"^([1-5])(?!\d)")


def parse_likert(value: Optional[str]) -> Optional[int]:
    text = (value or "").strip()
    if not text:
        return None
    if text in LIKERT_TEXT:
        return LIKERT_TEXT[text]
    match = LIKERT_NUMBER.match(text)  # 支援「5」或「5 非常同意」
    return int(match.group(1)) if match else None


def find_items(headers: Sequence[str]) -> Dict[str, List[Tuple[int, str, str]]]:
    """回傳 {構面代碼: [(欄位索引, 題號, 題目文字), ...]}。"""
    items: Dict[str, List[Tuple[int, str, str]]] = {letter: [] for letter in DIMENSIONS}
    for column, header in enumerate(headers):
        match = ITEM_HEADER.match(header)
        if not match:
            continue
        letter = match.group(1).upper()
        if letter in items:
            items[letter].append((column, f"{letter}{match.group(2)}", match.group(3).strip()))
    return items


def cronbach_alpha(matrix: Sequence[Sequence[float]]) -> Optional[float]:
    """matrix 每一列是一位受訪者、每一欄是一題（只含完整作答者）。"""
    if len(matrix) < 2 or len(matrix[0]) < 2:
        return None
    k = len(matrix[0])
    item_variance = sum(statistics.variance(column) for column in zip(*matrix))
    total_variance = statistics.variance([sum(row) for row in matrix])
    if total_variance == 0:
        return None
    return k / (k - 1) * (1 - item_variance / total_variance)


def describe_alpha(alpha: Optional[float]) -> str:
    if alpha is None:
        return "資料不足"
    for threshold, label in ((0.9, "極佳"), (0.8, "良好"), (0.7, "可接受"), (0.6, "尚可")):
        if alpha >= threshold:
            return label
    return "偏低"


def mean_sd(values: Sequence[float]) -> Tuple[Optional[float], Optional[float]]:
    if not values:
        return None, None
    return statistics.mean(values), (statistics.stdev(values) if len(values) > 1 else 0.0)


def fmt(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.2f}"


def cell(row: Sequence[str], column: int) -> Optional[int]:
    return parse_likert(row[column]) if column < len(row) else None


def analyze(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    items = find_items(headers)
    if not any(items.values()):
        raise ValueError("找不到題目欄位：請確認題目標題以 A1、B1、C1 這類題號開頭")

    summary = [
        "## 構面總覽",
        "",
        "| 構面 | 題數 | 有效樣本 | 平均數 | 標準差 | Cronbach's α | 信度 |",
        "|---|---|---|---|---|---|---|",
    ]
    details: List[str] = []

    for letter, name in DIMENSIONS.items():
        dimension_items = items[letter]
        if not dimension_items:
            continue

        details += [
            f"## {letter} {name}",
            "",
            "| 題號 | 題目 | 作答數 | 平均數 | 標準差 | 1 | 2 | 3 | 4 | 5 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for column, code, text in dimension_items:
            values = [v for v in (cell(row, column) for row in rows) if v is not None]
            mean, sd = mean_sd(values)
            counts = " | ".join(str(values.count(score)) for score in range(1, 6))
            details.append(f"| {code} | {text.replace('|', '｜')} | {len(values)} | {fmt(mean)} | {fmt(sd)} | {counts} |")
        details.append("")

        complete = []
        for row in rows:
            scores = [cell(row, column) for column, _, _ in dimension_items]
            if all(score is not None for score in scores):
                complete.append(scores)
        mean, sd = mean_sd([statistics.mean(scores) for scores in complete])
        alpha = cronbach_alpha(complete)
        summary.append(
            f"| {letter} {name} | {len(dimension_items)} | {len(complete)} | {fmt(mean)} | {fmt(sd)} "
            f"| {fmt(alpha)} | {describe_alpha(alpha)} |"
        )

    lines = ["# 問卷分析報告", "", f"回收問卷：{len(rows)} 份", ""]
    lines += summary
    lines += [
        "",
        "> 採 5 點量表（1 = 非常不同意，5 = 非常同意）。構面平均數為每位受訪者在該構面各題的平均，"
        "只計入該構面全部作答的樣本；Cronbach's α ≥ 0.7 一般視為信度可接受。",
        "",
    ]
    lines += details
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="分析問卷回覆 CSV")
    parser.add_argument("csv_path", help="問卷回覆 CSV 檔")
    parser.add_argument("-o", "--output", help="輸出 Markdown 報告的路徑（未指定則印在畫面上）")
    args = parser.parse_args(argv)

    with open(args.csv_path, encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
        rows = [row for row in reader if any(value.strip() for value in row)]

    report = analyze(headers, rows)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(report)
        print(f"已輸出報告：{args.output}")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        print(report)


if __name__ == "__main__":
    main()
