from __future__ import annotations

import csv
import io

import discord
from discord import app_commands
from discord.ext import commands

from cogs.quiz import LETTERS

EXPORT_HEADER = (
    "id", "answered_at_utc", "user_id", "username", "mode",
    "question_id", "category", "chosen", "correct", "elapsed_sec", "points",
)


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reload_questions", description="（管理員）重新載入題庫檔案")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reload_questions(self, interaction: discord.Interaction):
        bank = self.bot.bank
        try:
            count = bank.reload()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            await interaction.response.send_message(f"❌ 題庫載入失敗，仍使用原本的題庫：{exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ 已重新載入 {count} 題，共 {len(bank.categories())} 個分類。", ephemeral=True
        )

    @app_commands.command(name="export_answers", description="（管理員）匯出本伺服器所有作答紀錄 CSV")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def export_answers(self, interaction: discord.Interaction):
        rows = self.bot.db.export_answers(interaction.guild_id)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_HEADER)
        for row in rows:
            values = list(row)
            chosen_index = EXPORT_HEADER.index("chosen")
            values[chosen_index] = "" if row["chosen"] is None else LETTERS[row["chosen"]]
            writer.writerow(values)

        # utf-8-sig 讓 Excel 直接開啟時中文不會變亂碼
        data = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
        file = discord.File(data, filename=f"answers_{interaction.guild_id}.csv")
        await interaction.response.send_message(f"共 {len(rows)} 筆作答紀錄。", file=file, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
