from .condescend import Condescend

async def setup(bot):
    await bot.add_cog(Condescend(bot))
