import discord
import json
import os
import datetime
from typing import Optional
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class PoopScoop(commands.Cog):
    """Log when users poop."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.file_path = os.path.join(os.path.dirname(__file__), "poops.json")
        self.poops = []
        self.load_poops()

    def load_poops(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                self.poops = json.load(f)
        else:
            self.poops = []

    def save_poops(self):
        with open(self.file_path, "w") as f:
            json.dump(self.poops, f)

    # -- helpers ---------------------------------------------------------

    def _guild_entries(self, ctx):
        """Poop entries scoped to the current guild (or all in DMs)."""
        if ctx.guild:
            return [p for p in self.poops if p.get("guild_id") == ctx.guild.id]
        return list(self.poops)

    @staticmethod
    def _fmt(timestamp):
        """Render a UTC timestamp as a readable string."""
        dt = datetime.datetime.utcfromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    @staticmethod
    def _bar_chart(labels, values, width=18):
        """Build a monospace horizontal bar chart."""
        max_val = max(values) if values else 0
        lines = []
        for label, val in zip(labels, values):
            bar_len = round(val / max_val * width) if max_val else 0
            lines.append(f"{label:<4}│{'█' * bar_len} {val}")
        return "\n".join(lines)

    @staticmethod
    def _current_streak(timestamps):
        """Count consecutive UTC days with at least one poop, ending now."""
        days = {datetime.datetime.utcfromtimestamp(ts).date() for ts in timestamps}
        today = datetime.datetime.utcnow().date()
        if today in days:
            cursor = today
        elif (today - datetime.timedelta(days=1)) in days:
            cursor = today - datetime.timedelta(days=1)
        else:
            return 0
        streak = 0
        while cursor in days:
            streak += 1
            cursor -= datetime.timedelta(days=1)
        return streak

    # -- commands --------------------------------------------------------

    @commands.command(name="poop")
    async def poop(self, ctx):
        """Log that you pooped."""
        now = datetime.datetime.utcnow()
        entry = {
            "user_id": ctx.author.id,
            "user_name": str(ctx.author),
            "guild_id": ctx.guild.id if ctx.guild else None,
            "timestamp": now.timestamp(),
        }
        self.poops.append(entry)
        self.save_poops()

        await ctx.send(
            f"💩 Logged: {ctx.author.mention} pooped at {self._fmt(now.timestamp())}."
        )

    @commands.command(name="pooplog")
    async def pooplog(
        self, ctx, member: Optional[discord.Member] = None, limit: int = 10
    ):
        """Show recent poop log entries, optionally for one user."""
        limit = max(1, min(limit, 25))

        entries = self._guild_entries(ctx)
        if member:
            entries = [e for e in entries if e["user_id"] == member.id]

        if not entries:
            who = member.display_name if member else "anyone"
            await ctx.send(f"No poops logged for {who} yet. 🚽")
            return

        recent = entries[-limit:][::-1]
        title = (
            f"💩 Recent Poops — {member.display_name}"
            if member
            else "💩 Recent Poop Log"
        )
        embed = discord.Embed(title=title, color=discord.Color.dark_gold())
        for entry in recent:
            embed.add_field(
                name=entry.get("user_name", f"User {entry['user_id']}"),
                value=self._fmt(entry["timestamp"]),
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="mypoops")
    async def mypoops(self, ctx, member: Optional[discord.Member] = None):
        """Show a poop profile for yourself or another user."""
        member = member or ctx.author
        entries = sorted(
            (e for e in self._guild_entries(ctx) if e["user_id"] == member.id),
            key=lambda e: e["timestamp"],
        )
        if not entries:
            await ctx.send(f"{member.display_name} hasn't logged any poops yet. 🚽")
            return

        timestamps = [e["timestamp"] for e in entries]
        total = len(timestamps)
        first, last = timestamps[0], timestamps[-1]

        if total > 1:
            gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
            avg_gap = humanize_timedelta(seconds=int(sum(gaps) / len(gaps)))
            avg_str = avg_gap or "less than a second"
        else:
            avg_str = "N/A (need 2+ poops)"

        since_last = humanize_timedelta(
            seconds=int(datetime.datetime.utcnow().timestamp() - last)
        )
        streak = self._current_streak(timestamps)

        hour_counts = [0] * 24
        for ts in timestamps:
            hour_counts[datetime.datetime.utcfromtimestamp(ts).hour] += 1
        busiest_hour = hour_counts.index(max(hour_counts))

        embed = discord.Embed(
            title=f"💩 Poop Profile — {member.display_name}",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="Total poops", value=str(total), inline=True)
        embed.add_field(
            name="Current streak",
            value=f"{streak} day{'s' if streak != 1 else ''}",
            inline=True,
        )
        embed.add_field(
            name="Busiest hour", value=f"{busiest_hour:02d}:00 UTC", inline=True
        )
        embed.add_field(name="First poop", value=self._fmt(first), inline=False)
        embed.add_field(
            name="Last poop",
            value=f"{self._fmt(last)} ({since_last or 'just now'} ago)",
            inline=False,
        )
        embed.add_field(name="Average gap between poops", value=avg_str, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="poopstats")
    async def poopstats(self, ctx):
        """Show the poop leaderboard and server activity analytics."""
        entries = self._guild_entries(ctx)
        if not entries:
            await ctx.send("No poops logged yet. 🚽")
            return

        counts, names = {}, {}
        weekday_counts = [0] * 7
        hour_counts = [0] * 24
        week_ago = (
            datetime.datetime.utcnow() - datetime.timedelta(days=7)
        ).timestamp()
        last7 = 0

        for e in entries:
            uid = e["user_id"]
            counts[uid] = counts.get(uid, 0) + 1
            names[uid] = e.get("user_name", f"User {uid}")
            dt = datetime.datetime.utcfromtimestamp(e["timestamp"])
            weekday_counts[dt.weekday()] += 1
            hour_counts[dt.hour] += 1
            if e["timestamp"] >= week_ago:
                last7 += 1

        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        busiest_day = WEEKDAY_NAMES[weekday_counts.index(max(weekday_counts))]
        busiest_hour = hour_counts.index(max(hour_counts))

        embed = discord.Embed(
            title="🏆 Poop Leaderboard", color=discord.Color.dark_gold()
        )
        embed.description = "\n".join(
            f"{i}. {names[uid]} — {c} poop{'s' if c != 1 else ''}"
            for i, (uid, c) in enumerate(ranked[:10], start=1)
        )
        embed.add_field(
            name="📅 Activity by Weekday",
            value=f"```\n{self._bar_chart(WEEKDAY_NAMES, weekday_counts)}\n```",
            inline=False,
        )
        embed.add_field(
            name="📊 Summary",
            value=(
                f"Total poops: **{len(entries)}**\n"
                f"Last 7 days: **{last7}**\n"
                f"Busiest day: **{busiest_day}**\n"
                f"Busiest hour: **{busiest_hour:02d}:00 UTC**"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PoopScoop(bot))
