from .inspireme import InspireMe


async def setup(bot):
    await bot.add_cog(InspireMe(bot))
