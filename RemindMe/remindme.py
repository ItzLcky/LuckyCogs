import discord
import asyncio
import json
import os
import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

class RemindMe(commands.Cog):
    """Set reminders for yourself!"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.file_path = os.path.join(os.path.dirname(__file__), "reminders.json")
        self.reminders = []
        self.load_reminders()
        self.bot.loop.create_task(self.reminder_loop())

    def load_reminders(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                self.reminders = json.load(f)
        else:
            self.reminders = []

    def save_reminders(self):
        with open(self.file_path, "w") as f:
            json.dump(self.reminders, f)

    def parse_time(self, time_str):
        total_seconds = 0
        time_units = {'d': 86400, 'h': 3600, 'm': 60}
        current = ''
        for c in time_str:
            if c.isdigit():
                current += c
            elif c in time_units and current:
                total_seconds += int(current) * time_units[c]
                current = ''
        return total_seconds

    @commands.command()
    async def remindme(self, ctx, time: str, *, message: str):
        """Set a reminder. Time format: 1d2h30m"""
        seconds = self.parse_time(time)
        if seconds <= 0:
            await ctx.send("Time must be greater than zero.")
            return

        due = (datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)).timestamp()
        self.reminders.append({
            "user_id": ctx.author.id,
            "message": message,
            "due": due
        })
        self.save_reminders()

        await ctx.send(f"Got it! I'll remind you in {humanize_timedelta(timedelta=datetime.timedelta(seconds=seconds))}.")

    async def reminder_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.datetime.utcnow().timestamp()
            due_reminders = [r for r in self.reminders if r["due"] <= now]
            self.reminders = [r for r in self.reminders if r["due"] > now]

            for r in due_reminders:
                user = self.bot.get_user(r["user_id"])
                if user:
                    try:
                        await user.send(f"⏰ Reminder: {r['message']}")
                    except discord.Forbidden:
                        pass  # Cannot DM user
            if due_reminders:
                self.save_reminders()
            await asyncio.sleep(30)
