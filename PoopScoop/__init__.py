from .poopscoop import PoopScoop


async def setup(bot):
    await bot.add_cog(PoopScoop(bot))
