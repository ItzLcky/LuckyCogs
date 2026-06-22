import discord
import json
import os
import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEED_COOLDOWN = 60  # seconds between logs per user (anti-spam)
COUNT_MILESTONES = {10, 50, 100, 250, 500, 1000}
STREAK_MILESTONES = {7, 30, 100, 365}

# Single source of truth for delivery methods. Each method maps to its display
# label, emoji, the unit its amount is measured in, and the words that resolve
# to it. The unit is inferred from the method ("smart per-method default").
METHODS = {
    "flower": {
        "label": "Flower",
        "emoji": "🌿",
        "unit": "g",
        "aliases": [
            "smoke", "joint", "blunt", "spliff", "bong", "pipe",
            "bowl", "bubbler", "flower",
        ],
    },
    "vape": {
        "label": "Vape",
        "emoji": "💨",
        "unit": "hits",
        "aliases": ["vape", "cart", "cartridge", "pen", "vaporizer", "dryherb"],
    },
    "edible": {
        "label": "Edible",
        "emoji": "🍬",
        "unit": "mg",
        "aliases": ["edible", "gummy", "gummies", "brownie", "capsule", "tincture"],
    },
    "dab": {
        "label": "Concentrate",
        "emoji": "🍯",
        "unit": "hits",
        "aliases": [
            "dab", "dabs", "wax", "shatter", "rosin", "resin",
            "concentrate", "rig",
        ],
    },
}


class WeedTracker(commands.Cog):
    """Log cannabis sessions with method of delivery and amount."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.file_path = os.path.join(os.path.dirname(__file__), "weed.json")
        self.settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        self.sessions = []
        self.settings = {}
        self.load_sessions()
        self.load_settings()

    def load_sessions(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                self.sessions = json.load(f)
        else:
            self.sessions = []

    def save_sessions(self):
        with open(self.file_path, "w") as f:
            json.dump(self.sessions, f)

    def load_settings(self):
        if os.path.exists(self.settings_path):
            with open(self.settings_path, "r") as f:
                self.settings = json.load(f)
        else:
            self.settings = {}

    def save_settings(self):
        with open(self.settings_path, "w") as f:
            json.dump(self.settings, f)

    def _guild_tz(self, guild) -> datetime.tzinfo:
        """Return the configured timezone for a guild, or UTC if unset."""
        if guild is None:
            return datetime.timezone.utc
        name = self.settings.get("guild_tz", {}).get(str(guild.id))
        if not name:
            return datetime.timezone.utc
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            return datetime.timezone.utc

    def _guild_tz_name(self, guild) -> str:
        """Display name for the guild's configured timezone."""
        tz = self._guild_tz(guild)
        return getattr(tz, "key", "UTC")

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _utcnow():
        return datetime.datetime.now(datetime.timezone.utc)

    @staticmethod
    def _to_dt(timestamp):
        return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)

    def _guild_entries(self, ctx):
        """Sessions scoped to the current guild (or all in DMs)."""
        if ctx.guild:
            return [s for s in self.sessions if s.get("guild_id") == ctx.guild.id]
        return list(self.sessions)

    @staticmethod
    def _resolve_method(raw) -> Optional[str]:
        """Map a user-typed token to a canonical method key, or None."""
        if not raw:
            return None
        token = raw.strip().lower()
        for key, meta in METHODS.items():
            if token == key or token in meta["aliases"]:
                return key
        return None

    @staticmethod
    def _fmt_amount(entry) -> str:
        """Render an entry's amount + unit (e.g. "0.5 g"), or "" if no amount."""
        amount = entry.get("amount")
        if amount is None:
            return ""
        return f"{amount:g} {entry.get('unit', '')}".strip()

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
        """Count consecutive UTC days with at least one session, ending now."""
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

    @commands.group(name="weed", invoke_without_command=True)
    @commands.cooldown(1, WEED_COOLDOWN, commands.BucketType.user)
    async def weed(
        self, ctx, method: Optional[str] = None, *, rest: Optional[str] = None
    ):
        """Log a cannabis session.

        Usage: [p]weed <method> [amount] [note]
        Example: [p]weed joint 0.5 — or — [p]weed edible 10 sleepy gummy

        See [p]weed methods for the supported methods and their units.
        """
        if method is None:
            ctx.command.reset_cooldown(ctx)
            await ctx.send_help(ctx.command)
            return

        canonical = self._resolve_method(method)
        if canonical is None:
            ctx.command.reset_cooldown(ctx)
            supported = ", ".join(m["label"] for m in METHODS.values())
            await ctx.send(
                f"❓ Unknown method `{method}`. Supported methods: {supported}.\n"
                f"See `{ctx.clean_prefix}weed methods` for aliases and units."
            )
            return

        meta = METHODS[canonical]
        unit = meta["unit"]

        # rest = "[amount] [note]"; a leading number is the amount, the
        # remainder (or all of it, if it doesn't start with a number) is a note.
        amount = None
        note = None
        if rest:
            parts = rest.split(None, 1)
            try:
                amount = float(parts[0])
                note = parts[1] if len(parts) > 1 else None
            except ValueError:
                note = rest

        now = self._utcnow()
        entry = {
            "user_id": ctx.author.id,
            "user_name": str(ctx.author),
            "guild_id": ctx.guild.id if ctx.guild else None,
            "timestamp": now.timestamp(),
            "method": canonical,
            "unit": unit,
        }
        if amount is not None:
            entry["amount"] = amount
        if note:
            entry["note"] = note
        self.sessions.append(entry)
        self.save_sessions()

        amount_str = self._fmt_amount(entry)
        detail = f" — {amount_str}" if amount_str else ""
        lines = [
            f"{meta['emoji']} Logged a {meta['label'].lower()} session for "
            f"{ctx.author.mention}{detail} at {self._fmt(now.timestamp())}."
        ]
        if note:
            lines.append(f"📝 Note: {note}")

        # Milestones (per-guild, computed against this user's history).
        mine = sorted(
            (e for e in self._guild_entries(ctx) if e["user_id"] == ctx.author.id),
            key=lambda e: e["timestamp"],
        )
        total = len(mine)
        if total in COUNT_MILESTONES:
            lines.append(f"🎉 Milestone: that's **{total}** sessions logged!")

        # Streak milestones fire once, on the first session of the day.
        today_count = sum(
            1 for e in mine if self._to_dt(e["timestamp"]).date() == now.date()
        )
        if today_count == 1:
            streak = self._current_streak([e["timestamp"] for e in mine])
            if streak in STREAK_MILESTONES:
                lines.append(f"🔥 Streak milestone: **{streak}** days in a row!")

        await ctx.send("\n".join(lines))

    @weed.error
    async def weed_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = humanize_timedelta(seconds=int(error.retry_after)) or "a moment"
            await ctx.send(f"🌿 Slow down! Wait {retry} before logging another session.")
        else:
            raise error

    @weed.command(name="timezone", aliases=["tz"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def weed_timezone(self, ctx, *, name: Optional[str] = None):
        """Set the timezone used to bucket [p]weedstats weekday/hour stats.

        Examples:
          [p]weed timezone               → show current setting
          [p]weed timezone America/New_York
          [p]weed timezone Europe/London
          [p]weed timezone UTC           → reset to default
        """
        guild_tz = self.settings.setdefault("guild_tz", {})
        gid = str(ctx.guild.id)

        if name is None:
            current = guild_tz.get(gid, "UTC (default)")
            await ctx.send(
                f"📅 Weedstats timezone for this server: **{current}**\n"
                f"Use `{ctx.clean_prefix}weed timezone <IANA name>` to change "
                f"(e.g. `America/New_York`, `Europe/London`, `Asia/Tokyo`)."
            )
            return

        name = name.strip()
        if name.lower() in {"unset", "clear", "default", "utc"}:
            guild_tz.pop(gid, None)
            self.save_settings()
            await ctx.send("✅ Weedstats timezone reset to UTC.")
            return

        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError:
            await ctx.send(
                f"❌ Unknown timezone `{name}`. Use an IANA name like "
                f"`America/New_York` or `Europe/London`. See "
                f"<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>."
            )
            return

        guild_tz[gid] = name
        self.save_settings()
        await ctx.send(f"✅ Weedstats timezone set to **{name}**.")

    @weed.command(name="methods")
    async def weed_methods(self, ctx):
        """List the supported delivery methods, their aliases, and units."""
        embed = discord.Embed(
            title="🌿 Weed Tracker — Methods",
            description=(
                "Log a session with `"
                f"{ctx.clean_prefix}weed <method> [amount] [note]`. "
                "The amount's unit is set automatically by the method."
            ),
            color=discord.Color.green(),
        )
        for meta in METHODS.values():
            embed.add_field(
                name=f"{meta['emoji']} {meta['label']} — amount in {meta['unit']}",
                value="Aliases: " + ", ".join(f"`{a}`" for a in meta["aliases"]),
                inline=False,
            )
        await ctx.send(embed=embed)

    @weed.command(name="rules")
    async def weed_rules(self, ctx):
        """Show what counts as a session for tracking purposes."""
        embed = discord.Embed(
            title="🌿 Weed Tracker — Rules",
            description=(
                "**What counts as a session?**\n"
                "Each time you consume cannabis, log it once with the "
                "method you used and (optionally) how much."
            ),
            color=discord.Color.green(),
        )
        units = "\n".join(
            f"• {m['emoji']} **{m['label']}** — amount in **{m['unit']}**"
            for m in METHODS.values()
        )
        embed.add_field(name="🧪 Methods & units", value=units, inline=False)
        embed.add_field(
            name="📋 How to log",
            value=(
                f"• `{ctx.clean_prefix}weed <method>` — log a session\n"
                f"• `{ctx.clean_prefix}weed <method> <amount>` — log with amount "
                f"(e.g. `{ctx.clean_prefix}weed joint 0.5`)\n"
                f"• `{ctx.clean_prefix}weed <method> <amount> <note>` — add a note "
                f"(e.g. `{ctx.clean_prefix}weed edible 10 sleepy gummy`)\n"
                f"• One session = one log. Log each session separately.\n"
                f"• `{ctx.clean_prefix}weed methods` — see method aliases\n"
                f"• `{ctx.clean_prefix}weed undo` — remove your last log"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @weed.command(name="undo")
    async def weed_undo(self, ctx):
        """Remove your most recent session log entry."""
        mine = sorted(
            (e for e in self._guild_entries(ctx) if e["user_id"] == ctx.author.id),
            key=lambda e: e["timestamp"],
        )
        if not mine:
            await ctx.send("You have no sessions to undo. 🌿")
            return
        last = mine[-1]
        self.sessions.remove(last)
        self.save_sessions()
        await ctx.send(
            f"↩️ Removed your session logged at {self._fmt(last['timestamp'])}."
        )

    @commands.command(name="weedclear")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def weedclear(self, ctx):
        """Clear all session logs for this server (admin only)."""
        before = len(self.sessions)
        self.sessions = [s for s in self.sessions if s.get("guild_id") != ctx.guild.id]
        removed = before - len(self.sessions)
        self.save_sessions()
        await ctx.send(
            f"🧹 Cleared {removed} session log entr{'y' if removed == 1 else 'ies'}."
        )

    @commands.command(name="weedlog")
    async def weedlog(
        self, ctx, member: Optional[discord.Member] = None, limit: int = 10
    ):
        """Show recent session log entries, optionally for one user."""
        limit = max(1, min(limit, 25))

        entries = self._guild_entries(ctx)
        if member:
            entries = [e for e in entries if e["user_id"] == member.id]

        if not entries:
            who = member.display_name if member else "anyone"
            await ctx.send(f"No sessions logged for {who} yet. 🌿")
            return

        recent = entries[-limit:][::-1]
        title = (
            f"🌿 Recent Sessions — {member.display_name}"
            if member
            else "🌿 Recent Session Log"
        )
        embed = discord.Embed(title=title, color=discord.Color.green())
        for entry in recent:
            meta = METHODS.get(entry.get("method"), {})
            label = meta.get("label", entry.get("method", "Session"))
            emoji = meta.get("emoji", "🌿")
            amount_str = self._fmt_amount(entry)
            head = f"{emoji} {label}"
            if amount_str:
                head += f" — {amount_str}"
            value = f"{head}\n{self._fmt(entry['timestamp'])}"
            if entry.get("note"):
                value += f"\n📝 {entry['note']}"
            embed.add_field(
                name=entry.get("user_name", f"User {entry['user_id']}"),
                value=value,
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="myweed")
    async def myweed(self, ctx, member: Optional[discord.Member] = None):
        """Show a session profile for yourself or another user."""
        member = member or ctx.author
        entries = sorted(
            (e for e in self._guild_entries(ctx) if e["user_id"] == member.id),
            key=lambda e: e["timestamp"],
        )
        if not entries:
            await ctx.send(f"{member.display_name} hasn't logged any sessions yet. 🌿")
            return

        timestamps = [e["timestamp"] for e in entries]
        total = len(timestamps)
        first, last = timestamps[0], timestamps[-1]

        if total > 1:
            gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
            avg_gap = humanize_timedelta(seconds=int(sum(gaps) / len(gaps)))
            avg_str = avg_gap or "less than a second"
        else:
            avg_str = "N/A (need 2+ sessions)"

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

        # Per-method breakdown: count + summed amount, kept in each method's
        # own unit (units are never summed across methods).
        by_method = {}
        for e in entries:
            rec = by_method.setdefault(
                e.get("method"), {"count": 0, "amount": 0.0, "has_amount": False}
            )
            rec["count"] += 1
            if e.get("amount") is not None:
                rec["amount"] += e["amount"]
                rec["has_amount"] = True
        breakdown_lines = []
        for key, meta in METHODS.items():
            rec = by_method.get(key)
            if not rec:
                continue
            line = (
                f"{meta['emoji']} {meta['label']}: {rec['count']} "
                f"session{'s' if rec['count'] != 1 else ''}"
            )
            if rec["has_amount"]:
                line += f" · {rec['amount']:g} {meta['unit']}"
            breakdown_lines.append(line)

        embed = discord.Embed(
            title=f"🌿 Session Profile — {member.display_name}",
            color=discord.Color.green(),
        )
        embed.add_field(name="Total sessions", value=str(total), inline=True)
        embed.add_field(
            name="Current streak",
            value=f"{streak} day{'s' if streak != 1 else ''}",
            inline=True,
        )
        embed.add_field(
            name="Busiest hour", value=self._hour_tag(busiest_hour), inline=True
        )
        embed.add_field(
            name="Methods", value="\n".join(breakdown_lines), inline=False
        )
        embed.add_field(
            name="Most active day",
            value=(
                f"{best_day:%b %d, %Y} — {best_day_count} "
                f"session{'s' if best_day_count != 1 else ''}"
            ),
            inline=False,
        )
        embed.add_field(name="First session", value=self._fmt(first), inline=False)
        embed.add_field(
            name="Last session",
            value=f"{self._fmt(last)} ({since_last or 'just now'} ago)",
            inline=False,
        )
        embed.add_field(
            name="Average gap between sessions", value=avg_str, inline=False
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="weedstats")
    async def weedstats(self, ctx):
        """Show the session leaderboard and server activity analytics."""
        entries = self._guild_entries(ctx)
        if not entries:
            await ctx.send("No sessions logged yet. 🌿")
            return

        # Bucket weekday/hour in the guild's configured timezone so a session
        # logged at 8 PM Saturday local doesn't roll into Sunday on UTC.
        tz = self._guild_tz(ctx.guild)
        tz_name = self._guild_tz_name(ctx.guild)

        counts, names = {}, {}
        weekday_counts = [0] * 7
        hour_counts = [0] * 24
        method_counts = {key: 0 for key in METHODS}
        week_ago = (self._utcnow() - datetime.timedelta(days=7)).timestamp()
        last7 = 0

        for e in entries:
            uid = e["user_id"]
            counts[uid] = counts.get(uid, 0) + 1
            names[uid] = e.get("user_name", f"User {uid}")
            if e.get("method") in method_counts:
                method_counts[e["method"]] += 1
            dt = self._to_dt(e["timestamp"]).astimezone(tz)
            weekday_counts[dt.weekday()] += 1
            hour_counts[dt.hour] += 1
            if e["timestamp"] >= week_ago:
                last7 += 1

        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        busiest_day = WEEKDAY_NAMES[weekday_counts.index(max(weekday_counts))]
        busiest_hour = hour_counts.index(max(hour_counts))
        # Plain-text hour in the guild's TZ so it matches the chart's bucketing
        # (Discord's <t:...:t> tags would re-localize per viewer and drift from
        # the chart).
        hour_12 = (busiest_hour % 12) or 12
        ampm = "AM" if busiest_hour < 12 else "PM"
        busiest_hour_str = f"{hour_12} {ampm}"

        # Method-distribution chart: pre-pad labels to equal width so the bars
        # line up (the bar chart only pads to a 4-char minimum).
        method_labels = [METHODS[k]["label"] for k in METHODS]
        pad = max(len(label) for label in method_labels)
        padded_labels = [label.ljust(pad) for label in method_labels]
        method_values = [method_counts[k] for k in METHODS]

        embed = discord.Embed(
            title="🏆 Session Leaderboard", color=discord.Color.green()
        )
        embed.description = "\n".join(
            f"{i}. {names[uid]} — {c} session{'s' if c != 1 else ''}"
            for i, (uid, c) in enumerate(ranked[:10], start=1)
        )
        embed.add_field(
            name="📅 Activity by Weekday",
            value=f"```\n{self._bar_chart(WEEKDAY_NAMES, weekday_counts)}\n```",
            inline=False,
        )
        embed.add_field(
            name="🧪 Sessions by Method",
            value=f"```\n{self._bar_chart(padded_labels, method_values)}\n```",
            inline=False,
        )
        embed.add_field(
            name="📊 Summary",
            value=(
                f"Total sessions: **{len(entries)}**\n"
                f"Last 7 days: **{last7}**\n"
                f"Busiest day: **{busiest_day}**\n"
                f"Busiest hour: **{busiest_hour_str}**"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Weekday/hour stats in {tz_name}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WeedTracker(bot))
