from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from cogs.quiz import MEDALS

LEADERBOARD_SIZE = 10


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description=f"查看本伺服器積分排行榜（前 {LEADERBOARD_SIZE} 名）")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        db = self.bot.db
        top = db.leaderboard(interaction.guild_id, LEADERBOARD_SIZE)
        if not top:
            await interaction.response.send_message("目前還沒有人答題，快用 `/quiz` 搶下第一名！")
            return

        lines = []
        for place, stats in enumerate(top):
            prefix = MEDALS[place] if place < len(MEDALS) else f"`{place + 1:>2}.`"
            name = discord.utils.escape_markdown(stats.username)
            lines.append(
                f"{prefix} **{name}**　{stats.score} 分｜正確率 {stats.accuracy:.0%}｜最高連對 {stats.best_streak}"
            )
        embed = discord.Embed(title="🏆 積分排行榜", description="\n".join(lines), color=discord.Color.gold())

        me = db.get_user(interaction.guild_id, interaction.user.id)
        if me:
            embed.set_footer(text=f"你目前第 {db.rank(interaction.guild_id, me.user_id)} 名，共 {me.score} 分")
        else:
            embed.set_footer(text="你還沒有答題紀錄，用 /quiz 開始吧！")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stats", description="查看個人答題統計")
    @app_commands.describe(member="要查看的成員（留空則查看自己）")
    @app_commands.guild_only()
    async def stats(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        db = self.bot.db
        target = member or interaction.user
        stats = db.get_user(interaction.guild_id, target.id)
        if stats is None:
            await interaction.response.send_message(f"{target.display_name} 還沒有答題紀錄。", ephemeral=True)
            return

        embed = discord.Embed(title=f"📊 {target.display_name} 的答題統計", color=discord.Color.teal())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="總分", value=str(stats.score))
        embed.add_field(name="排名", value=f"第 {db.rank(interaction.guild_id, target.id)} 名")
        embed.add_field(name="正確率", value=f"{stats.accuracy:.0%}")
        embed.add_field(name="答題數", value=str(stats.answered))
        embed.add_field(name="答對數", value=str(stats.correct))
        embed.add_field(name="🔥 連對（目前／最高）", value=f"{stats.streak}／{stats.best_streak}")

        categories = db.category_stats(interaction.guild_id, target.id)
        if categories:
            value = "\n".join(
                f"{c.category}：{c.correct}/{c.answered}（{c.accuracy:.0%}）" for c in categories
            )
            embed.add_field(name="各分類表現", value=value, inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
