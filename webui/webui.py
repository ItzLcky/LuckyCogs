import asyncio
from redbot.core import commands
from redbot.core.bot import Red
import aiohttp
from aiohttp import web
import logging

log = logging.getLogger("red.WebUI")

class WebUI(commands.Cog):
    """Web UI backend server for the bot."""

    def __init__(self, bot: Red):
        self.bot = bot
        self._webserver = None
        self._runner = None
        self._site = None
        self._port = 8080  # You can make this configurable

        bot.loop.create_task(self.start_server())

    async def start_server(self):
        await self.bot.wait_until_ready()
        app = web.Application()
        app.router.add_get("/", self.handle_index)
        app.router.add_get("/api/ping", self.handle_ping)
        app.router.add_get("/api/user/{user_id}", self.handle_get_user)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await self._site.start()
        log.info(f"WebUI running on port {self._port}")

    async def cog_unload(self):
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    async def handle_index(self, request):
        return web.Response(text="WebUI is running!", content_type="text/plain")

    async def handle_ping(self, request):
        return web.json_response({"status": "ok", "message": "pong"})

    async def handle_get_user(self, request):
        user_id = int(request.match_info['user_id'])
        user = self.bot.get_user(user_id)
        if user:
            return web.json_response({"id": user.id, "name": str(user)})
        return web.json_response({"error": "User not found"}, status=404)
