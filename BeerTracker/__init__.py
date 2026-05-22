from .beertracker import BeerTracker


async def setup(bot):
    await bot.add_cog(BeerTracker(bot))
