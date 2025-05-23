from .webui import WebUI

async def setup(bot):
    await bot.add_cog(WebUI(bot))
