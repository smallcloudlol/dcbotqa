# Discord Bot 互動式問答系統

使用 Python + discord.py 製作的 Discord 問答 Bot，提供按鈕作答、即時回饋與排行榜，並附上使用者測試與問卷分析工具。

## 架構對照

| 架構 | 對應內容 |
|---|---|
| 系統設計／Discord Bot | `bot.py`（啟動、載入功能模組、同步斜線指令） |
| 系統設計／Python | `quizbot/`：題庫 `questions.py`、計分 `scoring.py`、判題 `game.py`、資料庫 `database.py`（SQLite） |
| 系統設計／Discord API | `cogs/`：斜線指令、Embed 訊息、按鈕互動（discord.py 2.x） |
| 功能設計／問答功能 | `/quiz` 個人答題、`/challenge` 全頻道挑戰、題庫 `data/questions.json` |
| 功能設計／即時回饋 | 作答後立即顯示對錯、按鈕上色、解析、得分明細、連對數與排名；倒數計時 |
| 功能設計／排行榜 | `/leaderboard` 積分排行、`/stats` 個人統計 |
| 使用者測試 | [`docs/使用者測試.md`](docs/使用者測試.md)：功能測試案例、使用體驗觀察表；`/export_answers` 匯出作答紀錄 |
| 問卷分析 | [`docs/問卷.md`](docs/問卷.md)：接受程度／互動體驗／使用意願量表；`tools/analyze_survey.py` 自動分析 |
| 結論 | 依實際測試與問卷結果撰寫 |

## 安裝與啟動

需要 Python 3.9 以上。

1. 到 [Discord Developer Portal](https://discord.com/developers/applications) 建立 Application → **Bot** 頁面取得 Token（本 Bot 不需要開啟任何 Privileged Intent）。
2. **OAuth2 → URL Generator** 勾選 scopes `bot`、`applications.commands`，權限勾選 `Send Messages`、`Embed Links`、`Attach Files`，用產生的網址把 Bot 邀請進伺服器。
3. 安裝套件並設定：

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # macOS / Linux：source .venv/bin/activate
   pip install -r requirements.txt
   copy .env.example .env          # macOS / Linux：cp .env.example .env
   ```

   編輯 `.env` 填入 `DISCORD_TOKEN`。建議也填入測試伺服器的 `GUILD_ID`（Discord 開啟開發者模式後，右鍵伺服器 →「複製伺服器 ID」），斜線指令會立即出現。

4. 啟動：`python bot.py`

## 指令

| 指令 | 說明 |
|---|---|
| `/quiz [分類]` | 個人答題，30 秒內按按鈕作答，答完立即看到結果，可按「下一題」繼續 |
| `/challenge [分類]` | 全頻道挑戰，每人限答一次，20 秒後公布選項分布與答對名單 |
| `/leaderboard` | 本伺服器前 10 名 |
| `/stats [成員]` | 總分、排名、正確率、連對紀錄、各分類表現 |
| `/help` | 使用說明 |
| `/reload_questions` | （管理伺服器權限）重新載入題庫 |
| `/export_answers` | （管理伺服器權限）匯出所有作答紀錄 CSV |

作答秒數可在 `.env` 的 `QUESTION_TIMEOUT`、`CHALLENGE_TIMEOUT` 調整。

## 計分規則

- 基本分：簡單 10／中等 20／困難 30
- 速度加成：`基本分 × 50% × 剩餘時間比例`（四捨五入）
- 連對加成：連續答對第 2 題起每題 +5，最多 +25
- 答錯或逾時 0 分，連對歸零

## 編輯題庫

`data/questions.json` 每題格式：

```json
{
  "id": "py-001",
  "category": "Python",
  "difficulty": "easy",
  "question": "Python 中用哪個關鍵字定義函式？",
  "options": ["def", "function", "func", "lambda"],
  "answer": 0,
  "explanation": "一般函式使用 def 定義。"
}
```

- `answer` 是正確選項的索引（從 0 開始）
- `difficulty`：`easy`／`medium`／`hard`
- 選項 2～5 個；`id` 不可重複
- 修改後執行 `/reload_questions` 即可生效，格式錯誤時會保留原題庫

## 資料

成績與作答紀錄存在 `data/quiz.db`（SQLite）：

- `users`：每位成員的總分、答題數、答對數、連對紀錄
- `answers`：每次作答的題目、選項、對錯、作答秒數、得分、時間（逾時的選項為空）

## 問卷分析

```bash
python tools/analyze_survey.py 問卷回覆.csv -o 問卷分析報告.md
```

量表題標題需以 `A1.`、`B1.`、`C1.` 等題號開頭，詳見 [`docs/問卷.md`](docs/問卷.md)。

## 測試

```bash
python -m unittest discover -s tests -v
```

涵蓋計分、題庫驗證、資料庫統計與排名、判題流程、問卷分析（不需要連線 Discord）。
