from .weedtracker import WeedTracker


async def setup(bot):
    await bot.add_cog(WeedTracker(bot))
