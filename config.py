import os

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None

QUESTION_TIMEOUT = int(os.getenv("QUESTION_TIMEOUT", "30"))
CHALLENGE_TIMEOUT = int(os.getenv("CHALLENGE_TIMEOUT", "20"))

DB_PATH = os.getenv("DB_PATH", "data/quiz.db")
QUESTIONS_PATH = os.getenv("QUESTIONS_PATH", "data/questions.json")
