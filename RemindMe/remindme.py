import discord
import asyncio
import json
import os
import datetime
from redbot.core import commands
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

    @commands.group(invoke_without_command=True)
    async def remindme(self, ctx):
        """Set reminders or view reminder commands."""
        prefix = ctx.clean_prefix
        embed = discord.Embed(
            title="⏰ Reminder Help Menu",
            description="Set a reminder or view reminder info.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Set a reminder", value=f"`{prefix}remindme set <time> <message>`", inline=False)
        embed.add_field(name="Example", value=f"`{prefix}remindme set 10m Take out the trash`", inline=False)
        embed.set_footer(text="Time format: d=day, h=hour, m=minute (e.g., 1d2h30m)")
        await ctx.send(embed=embed)

    @remindme.command()
    async def set(self, ctx, time: str, *, message: str):
        """Set a reminder. Time format: 1d2h30m"""
        seconds = self.parse_time(time)
        if seconds <= 0:
            await ctx.send("Time must be greater than zero.")
            return

        due = (datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)).timestamp()
        self.reminders.append({
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
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
                channel = self.bot.get_channel(r["channel_id"])
                user = self.bot.get_user(r["user_id"])
                if channel and user:
                    try:
                        await channel.send(f"{user.mention} ⏰ Reminder: {r['message']}")
                    except discord.Forbidden:
                        pass
            if due_reminders:
                self.save_reminders()
            await asyncio.sleep(30)
