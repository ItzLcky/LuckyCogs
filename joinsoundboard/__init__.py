from .joinsoundboard import JoinSoundboard


async def setup(bot):
    """Load the JoinSoundboard cog."""
    await bot.add_cog(JoinSoundboard(bot))
