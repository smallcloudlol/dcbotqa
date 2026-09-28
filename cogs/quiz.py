from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Set, Tuple

import discord
from discord import app_commands
from discord.ext import commands

import config
from quizbot.game import Outcome, settle_answer
from quizbot.questions import Question
from quizbot.scoring import BASE_POINTS, STREAK_BONUS_MAX, STREAK_BONUS_STEP

LETTERS = "ABCDE"
DIFFICULTY_LABELS = {"easy": "簡單", "medium": "中等", "hard": "困難"}
MEDALS = ("🥇", "🥈", "🥉")
RECENT_EXCLUDE = 10  # 抽題時避開最近答過的題數
RESULT_VIEW_TIMEOUT = 120  # 「下一題」按鈕保留秒數


# ---------- Embed 產生 ----------

def option_line(question: Question, index: int) -> str:
    return f"**{LETTERS[index]}.** {question.options[index]}"


def footer_text(question: Question) -> str:
    difficulty = DIFFICULTY_LABELS.get(question.difficulty, question.difficulty)
    return f"分類：{question.category}｜難度：{difficulty}"


def question_embed(question: Question, title: str, deadline: float) -> discord.Embed:
    options = "\n".join(option_line(question, i) for i in range(len(question.options)))
    embed = discord.Embed(
        title=title,
        description=f"{question.question}\n\n{options}\n\n⏳ 截止 <t:{int(deadline)}:R>",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=footer_text(question))
    return embed


def result_embed(question: Question, outcome: Outcome) -> discord.Embed:
    if outcome.chosen is None:
        title, color = "⏰ 時間到！", discord.Color.orange()
    elif outcome.correct:
        title, color = "✅ 答對了！", discord.Color.green()
    else:
        title, color = "❌ 答錯了", discord.Color.red()

    embed = discord.Embed(title=title, description=question.question, color=color)
    embed.add_field(name="正確答案", value=option_line(question, question.answer), inline=False)
    if outcome.chosen is not None and not outcome.correct:
        embed.add_field(name="你的答案", value=option_line(question, outcome.chosen), inline=False)
    if question.explanation:
        embed.add_field(name="💡 解析", value=question.explanation, inline=False)

    score = outcome.score
    if outcome.correct:
        detail = f"基本 {score.base}"
        if score.speed_bonus:
            detail += f" ＋ 速度 {score.speed_bonus}"
        if score.streak_bonus:
            detail += f" ＋ 連對 {score.streak_bonus}"
        embed.add_field(name="本題得分", value=f"**+{score.points}**（{detail}）", inline=False)
    else:
        embed.add_field(name="本題得分", value="+0", inline=False)

    stats = outcome.stats
    if outcome.chosen is not None:
        embed.add_field(name="作答時間", value=f"{outcome.elapsed:.1f} 秒")
    embed.add_field(name="🔥 連續答對", value=str(stats.streak))
    embed.add_field(name="總分", value=str(stats.score))
    embed.add_field(name="排名", value=f"第 {outcome.rank} 名")
    embed.add_field(name="正確率", value=f"{stats.accuracy:.0%}")
    embed.set_footer(text=footer_text(question))
    return embed


def challenge_result_embed(question: Question, responses: Dict[int, Outcome]) -> discord.Embed:
    total = len(responses)
    counts = [0] * len(question.options)
    for outcome in responses.values():
        counts[outcome.chosen] += 1

    lines = [question.question, ""]
    for index, option in enumerate(question.options):
        ratio = counts[index] / total if total else 0.0
        filled = round(ratio * 10)
        mark = "✅" if index == question.answer else "⬜"
        lines.append(f"{mark} **{LETTERS[index]}.** {option}")
        lines.append(f"`{'█' * filled}{'░' * (10 - filled)}` {counts[index]} 人（{ratio:.0%}）")

    embed = discord.Embed(title="🏁 挑戰結束！", description="\n".join(lines), color=discord.Color.gold())

    winners = sorted(
        ((user_id, outcome) for user_id, outcome in responses.items() if outcome.correct),
        key=lambda item: item[1].score.points,
        reverse=True,
    )
    if winners:
        rows = []
        for place, (user_id, outcome) in enumerate(winners[:10]):
            prefix = MEDALS[place] if place < len(MEDALS) else f"{place + 1}."
            rows.append(f"{prefix} <@{user_id}> **+{outcome.score.points}**（{outcome.elapsed:.1f} 秒）")
        if len(winners) > 10:
            rows.append(f"…還有 {len(winners) - 10} 人答對")
        value = "\n".join(rows)
    else:
        value = "沒有人答對 😢" if total else "沒有人作答 😢"
    embed.add_field(name=f"答對名單（{len(winners)}/{total}）", value=value, inline=False)

    if question.explanation:
        embed.add_field(name="💡 解析", value=question.explanation, inline=False)
    embed.set_footer(text=footer_text(question))
    return embed


# ---------- 按鈕與互動介面 ----------

class AnswerButton(discord.ui.Button):
    def __init__(self, index: int):
        super().__init__(label=LETTERS[index], style=discord.ButtonStyle.primary, row=0)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.on_answer(interaction, self.index)


def reveal_buttons(view: discord.ui.View, question: Question, chosen: Optional[int] = None) -> None:
    """停用作答按鈕：正解標綠色、答錯的選項標紅色。"""
    for item in view.children:
        if isinstance(item, AnswerButton):
            item.disabled = True
            if item.index == question.answer:
                item.style = discord.ButtonStyle.success
            elif item.index == chosen:
                item.style = discord.ButtonStyle.danger
            else:
                item.style = discord.ButtonStyle.secondary


class QuizView(discord.ui.View):
    """個人答題：只有出題者可以作答，計時由自己的 task 控制。"""

    def __init__(self, cog: Quiz, question: Question, owner: discord.abc.User, category: Optional[str]):
        super().__init__(timeout=None)
        self.cog = cog
        self.question = question
        self.owner = owner
        self.category = category
        self.time_limit = config.QUESTION_TIMEOUT
        self.started = time.monotonic()
        self.deadline = time.time() + self.time_limit
        self.message: Optional[discord.Message] = None
        self.finished = False
        self._timer: Optional[asyncio.Task] = None
        for index in range(len(question.options)):
            self.add_item(AnswerButton(index))

    def start_timer(self) -> None:
        if not self.finished:
            self._timer = asyncio.create_task(self._expire())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("這是其他人的題目喔！輸入 `/quiz` 開始你自己的挑戰。", ephemeral=True)
            return False
        return True

    def _finish(self, guild_id: int, chosen: Optional[int], elapsed: float) -> Tuple[discord.Embed, ResultView]:
        self.finished = True
        self.stop()
        self.cog.active_quizzes.discard((guild_id, self.owner.id))
        outcome = settle_answer(
            self.cog.bot.db,
            guild_id=guild_id,
            user_id=self.owner.id,
            username=self.owner.display_name,
            question=self.question,
            chosen=chosen,
            elapsed=elapsed,
            time_limit=self.time_limit,
            mode="quiz",
        )
        return result_embed(self.question, outcome), ResultView(self.cog, self.owner.id, self.question, chosen, self.category)

    async def on_answer(self, interaction: discord.Interaction, index: int):
        if self.finished:
            await interaction.response.send_message("這題已經結束了。", ephemeral=True)
            return
        if self._timer:
            self._timer.cancel()
        embed, view = self._finish(interaction.guild_id, index, time.monotonic() - self.started)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = self.message

    async def _expire(self):
        await asyncio.sleep(self.time_limit)
        if self.finished or self.message is None:
            return
        embed, view = self._finish(self.message.guild.id, None, self.time_limit)
        view.message = self.message
        try:
            await self.message.edit(embed=embed, view=view)
        except discord.HTTPException:
            view.stop()


class ResultView(discord.ui.View):
    """顯示答題結果：保留上色後的選項，並提供「下一題」。"""

    def __init__(self, cog: Quiz, owner_id: int, question: Question, chosen: Optional[int], category: Optional[str]):
        super().__init__(timeout=RESULT_VIEW_TIMEOUT)
        self.cog = cog
        self.owner_id = owner_id
        self.category = category
        self.message: Optional[discord.Message] = None
        for index in range(len(question.options)):
            self.add_item(AnswerButton(index))
        reveal_buttons(self, question, chosen)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("輸入 `/quiz` 開始你自己的題目吧！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="下一題", emoji="➡️", style=discord.ButtonStyle.primary, row=1)
    async def next_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog.start_quiz(interaction, self.category, followup=True)

    async def on_timeout(self):
        self.next_question.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ChallengeView(discord.ui.View):
    """全頻道挑戰：每人限答一次，時間到才公布答案與名單。"""

    def __init__(self, cog: Quiz, question: Question, channel_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.question = question
        self.channel_id = channel_id
        self.time_limit = config.CHALLENGE_TIMEOUT
        self.started = time.monotonic()
        self.deadline = time.time() + self.time_limit
        self.responses: Dict[int, Outcome] = {}
        self.message: Optional[discord.Message] = None
        self.finished = False
        self._timer: Optional[asyncio.Task] = None
        for index in range(len(question.options)):
            self.add_item(AnswerButton(index))

    def live_embed(self) -> discord.Embed:
        embed = question_embed(self.question, "⚔️ 全頻道挑戰！", self.deadline)
        embed.set_footer(text=f"{footer_text(self.question)}｜每人限答一次｜已有 {len(self.responses)} 人作答")
        return embed

    def start_timer(self) -> None:
        self._timer = asyncio.create_task(self._expire())

    async def on_answer(self, interaction: discord.Interaction, index: int):
        if self.finished:
            await interaction.response.send_message("這場挑戰已經結束了。", ephemeral=True)
            return
        user = interaction.user
        previous = self.responses.get(user.id)
        if previous is not None:
            await interaction.response.send_message(
                f"你已經選了 **{LETTERS[previous.chosen]}**，每人只能作答一次喔！", ephemeral=True
            )
            return

        outcome = settle_answer(
            self.cog.bot.db,
            guild_id=interaction.guild_id,
            user_id=user.id,
            username=user.display_name,
            question=self.question,
            chosen=index,
            elapsed=time.monotonic() - self.started,
            time_limit=self.time_limit,
            mode="challenge",
        )
        self.responses[user.id] = outcome
        await interaction.response.send_message(
            f"📨 已收到你的答案 **{LETTERS[index]}**（用時 {outcome.elapsed:.1f} 秒），倒數結束後公布結果！",
            ephemeral=True,
        )
        if self.message and not self.finished:
            try:
                await self.message.edit(embed=self.live_embed())
            except discord.HTTPException:
                pass

    async def _expire(self):
        try:
            await asyncio.sleep(self.time_limit)
        finally:
            self.finished = True
            self.stop()
            self.cog.active_challenges.discard(self.channel_id)
        reveal_buttons(self, self.question)
        if self.message:
            try:
                await self.message.edit(embed=challenge_result_embed(self.question, self.responses), view=self)
            except discord.HTTPException:
                pass


# ---------- 指令 ----------

class Quiz(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_quizzes: Set[Tuple[int, int]] = set()  # (guild_id, user_id)
        self.active_challenges: Set[int] = set()  # channel_id

    def category_choices(self, current: str) -> List[app_commands.Choice[str]]:
        current = current.lower()
        return [
            app_commands.Choice(name=category, value=category)
            for category in self.bot.bank.categories()
            if current in category.lower()
        ][:25]

    def unknown_category_message(self, category: Optional[str]) -> Optional[str]:
        categories = self.bot.bank.categories()
        if category and category not in categories:
            return f"找不到分類「{category}」。可用分類：{'、'.join(categories)}"
        return None

    async def start_quiz(self, interaction: discord.Interaction, category: Optional[str], *, followup: bool = False):
        async def send(**kwargs):
            if followup:
                return await interaction.followup.send(wait=True, **kwargs)
            await interaction.response.send_message(**kwargs)
            return await interaction.original_response()

        error = self.unknown_category_message(category)
        if error:
            await send(content=error, ephemeral=True)
            return

        key = (interaction.guild_id, interaction.user.id)
        if key in self.active_quizzes:
            await send(content="你還有一題沒答完，先完成它吧！", ephemeral=True)
            return

        recent = self.bot.db.recent_question_ids(interaction.guild_id, interaction.user.id, RECENT_EXCLUDE)
        question = self.bot.bank.random(category, exclude=recent)
        if question is None:
            await send(content="題庫目前沒有題目。", ephemeral=True)
            return

        self.active_quizzes.add(key)
        view = QuizView(self, question, interaction.user, category)
        try:
            view.message = await send(embed=question_embed(question, "📝 個人答題", view.deadline), view=view)
        except discord.HTTPException:
            self.active_quizzes.discard(key)
            view.stop()
            raise
        view.start_timer()

    @app_commands.command(name="quiz", description="個人答題：隨機出一題，作答後立即看到結果")
    @app_commands.describe(category="題目分類（留空則隨機）")
    @app_commands.guild_only()
    async def quiz(self, interaction: discord.Interaction, category: Optional[str] = None):
        await self.start_quiz(interaction, category)

    @quiz.autocomplete("category")
    async def quiz_category(self, interaction: discord.Interaction, current: str):
        return self.category_choices(current)

    @app_commands.command(name="challenge", description="全頻道挑戰：所有人一起作答，時間到公布結果")
    @app_commands.describe(category="題目分類（留空則隨機）")
    @app_commands.guild_only()
    async def challenge(self, interaction: discord.Interaction, category: Optional[str] = None):
        error = self.unknown_category_message(category)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        channel_id = interaction.channel_id
        if channel_id in self.active_challenges:
            await interaction.response.send_message("這個頻道已經有一場挑戰正在進行中！", ephemeral=True)
            return

        question = self.bot.bank.random(category)
        self.active_challenges.add(channel_id)
        view = ChallengeView(self, question, channel_id)
        try:
            await interaction.response.send_message(embed=view.live_embed(), view=view)
            view.message = await interaction.original_response()
        except discord.HTTPException:
            self.active_challenges.discard(channel_id)
            view.stop()
            raise
        view.start_timer()

    @challenge.autocomplete("category")
    async def challenge_category(self, interaction: discord.Interaction, current: str):
        return self.category_choices(current)

    @app_commands.command(name="help", description="查看問答 Bot 的使用說明")
    async def help_command(self, interaction: discord.Interaction):
        points = "／".join(f"{DIFFICULTY_LABELS[level]} {value}" for level, value in BASE_POINTS.items())
        embed = discord.Embed(title="📖 問答 Bot 使用說明", color=discord.Color.blurple())
        embed.add_field(
            name="/quiz [分類]",
            value=f"個人答題。{config.QUESTION_TIMEOUT} 秒內按按鈕作答，答完立即顯示對錯、解析與得分。",
            inline=False,
        )
        embed.add_field(
            name="/challenge [分類]",
            value=f"全頻道挑戰。所有人 {config.CHALLENGE_TIMEOUT} 秒內各答一次，時間到公布答案分布與答對名單。",
            inline=False,
        )
        embed.add_field(name="/leaderboard", value="查看本伺服器積分排行榜。", inline=False)
        embed.add_field(name="/stats [成員]", value="查看答題數、正確率、連對紀錄與各分類表現。", inline=False)
        embed.add_field(
            name="計分方式",
            value=(
                f"答對得基本分（{points}）\n"
                "＋ 速度加成：越快作答越高，最多再加基本分的 50%\n"
                f"＋ 連對加成：連續答對第 2 題起每題 +{STREAK_BONUS_STEP}，最多 +{STREAK_BONUS_MAX}\n"
                "答錯或逾時得 0 分，連對歸零"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Quiz(bot))
