import discord
import json
import os
import datetime
from redbot.core import commands
from redbot.core.bot import Red


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

        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        await ctx.send(
            f"💩 Logged: {ctx.author.mention} pooped at {timestamp_str}."
        )

    @commands.command(name="pooplog")
    async def pooplog(self, ctx, limit: int = 10):
        """Show the most recent poop log entries."""
        if limit < 1:
            limit = 1
        if limit > 50:
            limit = 50

        if ctx.guild:
            entries = [p for p in self.poops if p.get("guild_id") == ctx.guild.id]
        else:
            entries = list(self.poops)

        if not entries:
            await ctx.send("No poops logged yet. 🚽")
            return

        recent = entries[-limit:][::-1]
        embed = discord.Embed(
            title="💩 Recent Poop Log",
            color=discord.Color.dark_gold(),
        )
        for entry in recent:
            ts = datetime.datetime.utcfromtimestamp(entry["timestamp"])
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
            embed.add_field(
                name=entry.get("user_name", f"User {entry['user_id']}"),
                value=ts_str,
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="poopstats")
    async def poopstats(self, ctx):
        """Show poop counts per user."""
        if ctx.guild:
            entries = [p for p in self.poops if p.get("guild_id") == ctx.guild.id]
        else:
            entries = list(self.poops)

        if not entries:
            await ctx.send("No poops logged yet. 🚽")
            return

        counts = {}
        names = {}
        for entry in entries:
            uid = entry["user_id"]
            counts[uid] = counts.get(uid, 0) + 1
            names[uid] = entry.get("user_name", f"User {uid}")

        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        embed = discord.Embed(
            title="🏆 Poop Leaderboard",
            color=discord.Color.dark_gold(),
        )
        for i, (uid, count) in enumerate(ranked[:10], start=1):
            embed.add_field(
                name=f"{i}. {names[uid]}",
                value=f"{count} poop{'s' if count != 1 else ''}",
                inline=False,
            )
        await ctx.send(embed=embed)
