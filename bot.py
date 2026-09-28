import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from quizbot.database import Database
from quizbot.questions import QuestionBank

log = logging.getLogger("quizbot")

EXTENSIONS = ("cogs.quiz", "cogs.leaderboard", "cogs.admin")


class QuizBot(commands.Bot):
    def __init__(self):
        # 只使用斜線指令與按鈕，不需要任何 Privileged Intent
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())
        self.db = Database(config.DB_PATH)
        self.bank = QuestionBank(config.QUESTIONS_PATH)

    async def setup_hook(self):
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        self.tree.error(self.on_app_command_error)

        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
        else:
            synced = await self.tree.sync()
        log.info("已同步 %d 個斜線指令，題庫共 %d 題", len(synced), len(self.bank.questions))

    async def on_ready(self):
        log.info("已登入：%s (ID %s)", self.user, self.user.id)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            message = "你沒有權限使用這個指令。"
        else:
            log.error("指令執行失敗", exc_info=error)
            message = "發生錯誤，請稍後再試。"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

    async def close(self):
        await super().close()
        self.db.close()


def main():
    if not config.TOKEN:
        raise SystemExit("請先在 .env 設定 DISCORD_TOKEN（可參考 .env.example）")
    discord.utils.setup_logging(root=True)
    QuizBot().run(config.TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
