import discord
import json
import os
import datetime
from typing import Optional
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BEER_COOLDOWN = 60  # seconds between logs per user (anti-spam)
COUNT_MILESTONES = {10, 50, 100, 250, 500, 1000}
STREAK_MILESTONES = {7, 30, 100, 365}


class BeerTracker(commands.Cog):
    """Log the beers users drink."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.file_path = os.path.join(os.path.dirname(__file__), "beers.json")
        self.beers = []
        self.load_beers()

    def load_beers(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                self.beers = json.load(f)
        else:
            self.beers = []

    def save_beers(self):
        with open(self.file_path, "w") as f:
            json.dump(self.beers, f)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _utcnow():
        return datetime.datetime.now(datetime.timezone.utc)

    @staticmethod
    def _to_dt(timestamp):
        return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)

    def _guild_entries(self, ctx):
        """Beer entries scoped to the current guild (or all in DMs)."""
        if ctx.guild:
            return [b for b in self.beers if b.get("guild_id") == ctx.guild.id]
        return list(self.beers)

    @staticmethod
    def _fmt(timestamp, style="f"):
        """Render a stored UTC timestamp as a Discord timestamp tag.

        Discord displays these in each viewer's own local timezone.
        Style "f" = date and time, "R" = relative (e.g. "2 hours ago").
        """
        return f"<t:{int(timestamp)}:{style}>"

    @classmethod
    def _hour_tag(cls, hour):
        """Render a UTC hour-of-day as a Discord time tag.

        Anchors the hour to today's date so Discord shows it in each
        viewer's local timezone (time-only, e.g. "1:00 PM").
        """
        dt = cls._utcnow().replace(hour=hour, minute=0, second=0, microsecond=0)
        return f"<t:{int(dt.timestamp())}:t>"

    @staticmethod
    def _bar_chart(labels, values, width=18):
        """Build a monospace horizontal bar chart."""
        max_val = max(values) if values else 0
        lines = []
        for label, val in zip(labels, values):
            bar_len = round(val / max_val * width) if max_val else 0
            lines.append(f"{label:<4}│{'█' * bar_len} {val}")
        return "\n".join(lines)

    @classmethod
    def _current_streak(cls, timestamps):
        """Count consecutive UTC days with at least one beer, ending now."""
        days = {cls._to_dt(ts).date() for ts in timestamps}
        today = cls._utcnow().date()
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

    @commands.group(name="beer", invoke_without_command=True)
    @commands.cooldown(1, BEER_COOLDOWN, commands.BucketType.user)
    async def beer(self, ctx, *, note: Optional[str] = None):
        """Log a beer you drank. Optionally name the beer."""
        now = self._utcnow()
        entry = {
            "user_id": ctx.author.id,
            "user_name": str(ctx.author),
            "guild_id": ctx.guild.id if ctx.guild else None,
            "timestamp": now.timestamp(),
        }
        if note:
            entry["note"] = note
        self.beers.append(entry)
        self.save_beers()

        lines = [
            f"🍺 Cheers! {ctx.author.mention} logged a beer at {self._fmt(now.timestamp())}."
        ]
        if note:
            lines.append(f"📝 Beer: {note}")

        # Milestones (per-guild, computed against this user's history).
        mine = sorted(
            (e for e in self._guild_entries(ctx) if e["user_id"] == ctx.author.id),
            key=lambda e: e["timestamp"],
        )
        total = len(mine)
        if total in COUNT_MILESTONES:
            lines.append(f"🎉 Milestone: that's **{total}** beers logged!")

        # Streak milestones fire once, on the first beer of the day.
        today_count = sum(
            1 for e in mine if self._to_dt(e["timestamp"]).date() == now.date()
        )
        if today_count == 1:
            streak = self._current_streak([e["timestamp"] for e in mine])
            if streak in STREAK_MILESTONES:
                lines.append(f"🔥 Streak milestone: **{streak}** days in a row!")

        await ctx.send("\n".join(lines))

    @beer.error
    async def beer_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = humanize_timedelta(seconds=int(error.retry_after)) or "a moment"
            await ctx.send(f"🍺 Slow down! Wait {retry} before logging another beer.")
        else:
            raise error

    @beer.command(name="undo")
    async def beer_undo(self, ctx):
        """Remove your most recent beer log entry."""
        mine = sorted(
            (e for e in self._guild_entries(ctx) if e["user_id"] == ctx.author.id),
            key=lambda e: e["timestamp"],
        )
        if not mine:
            await ctx.send("You have no beers to undo. 🍺")
            return
        last = mine[-1]
        self.beers.remove(last)
        self.save_beers()
        await ctx.send(f"↩️ Removed your beer logged at {self._fmt(last['timestamp'])}.")

    @commands.command(name="beerclear")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def beerclear(self, ctx):
        """Clear all beer logs for this server (admin only)."""
        before = len(self.beers)
        self.beers = [b for b in self.beers if b.get("guild_id") != ctx.guild.id]
        removed = before - len(self.beers)
        self.save_beers()
        await ctx.send(
            f"🧹 Cleared {removed} beer log entr{'y' if removed == 1 else 'ies'}."
        )

    @commands.command(name="beerlog")
    async def beerlog(
        self, ctx, member: Optional[discord.Member] = None, limit: int = 10
    ):
        """Show recent beer log entries, optionally for one user."""
        limit = max(1, min(limit, 25))

        entries = self._guild_entries(ctx)
        if member:
            entries = [e for e in entries if e["user_id"] == member.id]

        if not entries:
            who = member.display_name if member else "anyone"
            await ctx.send(f"No beers logged for {who} yet. 🍺")
            return

        recent = entries[-limit:][::-1]
        title = (
            f"🍺 Recent Beers — {member.display_name}"
            if member
            else "🍺 Recent Beer Log"
        )
        embed = discord.Embed(title=title, color=discord.Color.gold())
        for entry in recent:
            value = self._fmt(entry["timestamp"])
            if entry.get("note"):
                value += f"\n📝 {entry['note']}"
            embed.add_field(
                name=entry.get("user_name", f"User {entry['user_id']}"),
                value=value,
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="mybeers")
    async def mybeers(self, ctx, member: Optional[discord.Member] = None):
        """Show a beer profile for yourself or another user."""
        member = member or ctx.author
        entries = sorted(
            (e for e in self._guild_entries(ctx) if e["user_id"] == member.id),
            key=lambda e: e["timestamp"],
        )
        if not entries:
            await ctx.send(f"{member.display_name} hasn't logged any beers yet. 🍺")
            return

        timestamps = [e["timestamp"] for e in entries]
        total = len(timestamps)
        first, last = timestamps[0], timestamps[-1]

        if total > 1:
            gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
            avg_gap = humanize_timedelta(seconds=int(sum(gaps) / len(gaps)))
            avg_str = avg_gap or "less than a second"
        else:
            avg_str = "N/A (need 2+ beers)"

        since_last = humanize_timedelta(
            seconds=int(self._utcnow().timestamp() - last)
        )
        streak = self._current_streak(timestamps)

        hour_counts = [0] * 24
        day_counts = {}
        for ts in timestamps:
            dt = self._to_dt(ts)
            hour_counts[dt.hour] += 1
            day_counts[dt.date()] = day_counts.get(dt.date(), 0) + 1
        busiest_hour = hour_counts.index(max(hour_counts))
        best_day, best_day_count = max(day_counts.items(), key=lambda x: x[1])

        embed = discord.Embed(
            title=f"🍺 Beer Profile — {member.display_name}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Total beers", value=str(total), inline=True)
        embed.add_field(
            name="Current streak",
            value=f"{streak} day{'s' if streak != 1 else ''}",
            inline=True,
        )
        embed.add_field(
            name="Busiest hour", value=self._hour_tag(busiest_hour), inline=True
        )
        embed.add_field(
            name="Most active day",
            value=(
                f"{best_day:%b %d, %Y} — {best_day_count} "
                f"beer{'s' if best_day_count != 1 else ''}"
            ),
            inline=False,
        )
        embed.add_field(name="First beer", value=self._fmt(first), inline=False)
        embed.add_field(
            name="Last beer",
            value=f"{self._fmt(last)} ({since_last or 'just now'} ago)",
            inline=False,
        )
        embed.add_field(name="Average gap between beers", value=avg_str, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="beerstats")
    async def beerstats(self, ctx):
        """Show the beer leaderboard and server activity analytics."""
        entries = self._guild_entries(ctx)
        if not entries:
            await ctx.send("No beers logged yet. 🍺")
            return

        counts, names = {}, {}
        weekday_counts = [0] * 7
        hour_counts = [0] * 24
        week_ago = (self._utcnow() - datetime.timedelta(days=7)).timestamp()
        last7 = 0

        for e in entries:
            uid = e["user_id"]
            counts[uid] = counts.get(uid, 0) + 1
            names[uid] = e.get("user_name", f"User {uid}")
            dt = self._to_dt(e["timestamp"])
            weekday_counts[dt.weekday()] += 1
            hour_counts[dt.hour] += 1
            if e["timestamp"] >= week_ago:
                last7 += 1

        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        busiest_day = WEEKDAY_NAMES[weekday_counts.index(max(weekday_counts))]
        busiest_hour = hour_counts.index(max(hour_counts))

        embed = discord.Embed(
            title="🏆 Beer Leaderboard", color=discord.Color.gold()
        )
        embed.description = "\n".join(
            f"{i}. {names[uid]} — {c} beer{'s' if c != 1 else ''}"
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
                f"Total beers: **{len(entries)}**\n"
                f"Last 7 days: **{last7}**\n"
                f"Busiest day: **{busiest_day}**\n"
                f"Busiest hour: {self._hour_tag(busiest_hour)}"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(BeerTracker(bot))
