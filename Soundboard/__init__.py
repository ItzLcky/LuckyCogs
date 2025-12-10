from .join_soundboard import JoinSoundboard


async def setup(bot):
    await bot.add_cog(JoinSoundboard(bot))
