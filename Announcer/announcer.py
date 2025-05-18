import discord
import asyncio
import json
import os
from datetime import datetime, timedelta
from redbot.core import commands, checks
from redbot.core.bot import Red

class Announcer(commands.Cog):
    """Schedule announcements with optional repeats and role mentions."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.file_path = os.path.join(os.path.dirname(__file__), "announcements.json")
        self.announcements = []
        self.load_announcements()
        self.bot.loop.create_task(self.announcement_loop())

    def load_announcements(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                self.announcements = json.load(f)
        else:
            self.announcements = []

    def save_announcements(self):
        with open(self.file_path, "w") as f:
            json.dump(self.announcements, f)

    def parse_repeat(self, repeat_str):
        intervals = {"daily": 86400, "hourly": 3600, "weekly": 604800}
        return intervals.get(repeat_str.lower())

    @commands.group()
    @checks.admin()
    async def announce(self, ctx):
        """Manage scheduled announcements."""
        pass

    @announce.command()
    async def schedule(self, ctx, datetime_str: str, channel: discord.TextChannel, role: discord.Role = None, repeat: str = None, *, message: str):
        """
        Schedule an announcement.
        datetime_str format: YYYY-MM-DD_HH:MM (24-hour)
        Optional: role mention, repeat (daily/hourly/weekly)
        """
        try:
            dt = datetime.strptime(datetime_str, "%Y-%m-%d_%H:%M")
        except ValueError:
            await ctx.send("Invalid datetime format. Use `YYYY-MM-DD_HH:MM`.")
            return

        repeat_interval = self.parse_repeat(repeat) if repeat else None

        announcement = {
            "channel_id": channel.id,
            "role_id": role.id if role else None,
            "message": message,
            "time": dt.timestamp(),
            "repeat": repeat_interval
        }

        self.announcements.append(announcement)
        self.save_announcements()
        await ctx.send(f"✅ Announcement scheduled for {dt} in {channel.mention}.")

    @announce.command()
    async def list(self, ctx):
        """List all scheduled announcements."""
        if not self.announcements:
            await ctx.send("No scheduled announcements.")
            return

        msg = ""
        for idx, a in enumerate(self.announcements):
            time = datetime.fromtimestamp(a["time"]).strftime("%Y-%m-%d %H:%M")
            ch = self.bot.get_channel(a["channel_id"])
            role = f"<@&{a['role_id']}>" if a.get("role_id") else "None"
            repeat = a["repeat"]
            msg += f"**{idx}** | {time} | {ch.mention if ch else 'Unknown'} | Role: {role} | Repeat: {repeat} | Msg: {a['message'][:30]}...
"

        await ctx.send(msg)

    @announce.command()
    async def delete(self, ctx, index: int):
        """Delete a scheduled announcement."""
        try:
            removed = self.announcements.pop(index)
            self.save_announcements()
            await ctx.send("✅ Announcement deleted.")
        except IndexError:
            await ctx.send("Invalid index.")

    async def announcement_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.utcnow().timestamp()
            due = [a for a in self.announcements if a["time"] <= now]
            self.announcements = [a for a in self.announcements if a["time"] > now or a["repeat"]]

            for a in due:
                channel = self.bot.get_channel(a["channel_id"])
                if not channel:
                    continue

                role_mention = f"<@&{a['role_id']}>" if a.get("role_id") else ""
                try:
                    await channel.send(f"{role_mention} {a['message']}")
                except discord.Forbidden:
                    continue

                if a.get("repeat"):
                    a["time"] = now + a["repeat"]
                    self.announcements.append(a)

            if due:
                self.save_announcements()
            await asyncio.sleep(60)
