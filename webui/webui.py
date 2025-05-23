import asyncio
from redbot.core import commands
from redbot.core.bot import Red
import aiohttp
from aiohttp import web
import logging
from pathlib import Path

log = logging.getLogger("red.WebUI")

class WebUI(commands.Cog):
    """Web UI backend server for the bot."""

    def __init__(self, bot: Red):
        self.bot = bot
        self._runner = None
        self._site = None
        self._port = 8080  # Change this if needed

        bot.loop.create_task(self.start_server())

    async def start_server(self):
        await self.bot.wait_until_ready()
        app = web.Application()
        
        # API routes
        app.router.add_get("/api/ping", self.handle_ping)
        app.router.add_get("/api/user/{user_id}", self.handle_get_user)

        # Static file serving
        static_path = Path(__file__).parent / "static"
        if static_path.exists():
            app.router.add_static("/", static_path, show_index=True)
            log.info(f"Serving static files from {static_path}")
        else:
            log.warning("Static folder not found at %s", static_path)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await self._site.start()
        log.info(f"WebUI is running on port {self._port}")

    async def cog_unload(self):
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    async def handle_ping(self, request):
        return web.json_response({"status": "ok", "message": "pong"})

    async def handle_get_user(self, request):
        user_id_str = request.match_info.get('user_id')
        try:
            user_id = int(user_id_str)
        except ValueError:
            return web.json_response({"error": "Invalid user ID"}, status=400)

        user = self.bot.get_user(user_id)
        if user:
            return web.json_response({"id": user.id, "name": str(user)})
        return web.json_response({"error": "User not found"}, status=404)
