from redbot.core import commands

class MyCoolCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def hello(self, ctx):
        """Say hello!"""
        await ctx.send("Hello, world!")

def setup(bot):
    bot.add_cog(LuckyCogs(bot))
