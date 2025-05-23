import asyncio
import logging
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
from redbot.core import commands, Config
from redbot.core.bot import Red
import discord

log = logging.getLogger("red.WebUI")

DISCORD_API_BASE = "https://discord.com/api"


class WebUI(commands.Cog):
    """Web UI backend server for the bot."""

    def __init__(self, bot: Red):
        self.bot = bot
        self._runner = None
        self._site = None
        self._port = 8080

        self.config = Config.get_conf(self, identifier=6543210)
        default_global = {
            "client_id": None,
            "client_secret": None,
            "redirect_uri": "http://localhost:8080/oauth/callback",
        }
        self.config.register_global(**default_global)

        self._authed_users = set()  # Store authed user IDs temporarily

        bot.loop.create_task(self.start_server())

    async def start_server(self):
        await self.bot.wait_until_ready()
        app = web.Application()

        # API routes
        app.router.add_get("/api/ping", self.handle_ping)
        app.router.add_get("/api/user/{user_id}", self.handle_get_user)
        app.router.add_get("/api/guilds", self.handle_get_guilds)
        app.router.add_get("/api/stats", self.handle_stats)

        # Admin + OAuth
        app.router.add_get("/admin", self.handle_admin_page)
        app.router.add_get("/oauth/login", self.handle_oauth_login)
        app.router.add_get("/oauth/callback", self.handle_oauth_callback)

        # Serve static files
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

    # === API ROUTES ===

    async def handle_ping(self, request):
        return web.json_response({"status": "ok", "message": "pong"})

    async def handle_get_user(self, request):
        user_id_str = request.match_info.get("user_id")
        try:
            user_id = int(user_id_str)
        except ValueError:
            return web.json_response({"error": "Invalid user ID"}, status=400)

        user = self.bot.get_user(user_id)
        if user:
            return web.json_response({"id": user.id, "name": str(user)})
        return web.json_response({"error": "User not found"}, status=404)

    async def handle_get_guilds(self, request):
        auth_header = request.headers.get("X-User-ID")
        if not auth_header or int(auth_header) not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)

        guilds = self.bot.guilds
        data = [
            {
                "id": str(g.id),
                "name": g.name,
                "member_count": g.member_count,
            }
            for g in guilds
        ]
        return web.json_response({"guilds": data})

    async def handle_stats(self, request):
        auth_header = request.headers.get("X-User-ID")
        if not auth_header or int(auth_header) not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)

        total_users = sum(g.member_count for g in self.bot.guilds)
        total_guilds = len(self.bot.guilds)

        return web.json_response({
            "total_users": total_users,
            "total_guilds": total_guilds,
            "cogs_loaded": list(self.bot.cogs.keys()),
        })

    # === STATIC ADMIN PAGE ===

    async def handle_admin_page(self, request):
        html_path = Path(__file__).parent / "static" / "admin.html"
        if html_path.exists():
            return web.FileResponse(html_path)
        return web.Response(text="Admin page not found", status=404)

    # === OAUTH2 LOGIN ===

    async def handle_oauth_login(self, request):
        client_id = await self.config.client_id()
        redirect_uri = await self.config.redirect_uri()

        log.info(f"[WebUI] OAuth Login: client_id={client_id}, redirect_uri={redirect_uri}")

        if not client_id or not redirect_uri:
            return web.Response(text="OAuth not configured", status=500)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "identify",
        }
        url = f"{DISCORD_API_BASE}/oauth2/authorize?" + urlencode(params)
        return web.HTTPFound(url)

    async def handle_oauth_callback(self, request):
        code = request.query.get("code")
        if not code:
            return web.Response(text="Missing code", status=400)

        client_id = await self.config.client_id()
        client_secret = await self.config.client_secret()
        redirect_uri = await self.config.redirect_uri()

        if not client_id or not client_secret:
            return web.Response(text="OAuth not configured", status=500)

        async with aiohttp.ClientSession() as session:
            token_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "scope": "identify",
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            async with session.post(
                f"{DISCORD_API_BASE}/oauth2/token", data=token_data, headers=headers
            ) as token_resp:
                token_json = await token_resp.json()
                access_token = token_json.get("access_token")

            if not access_token:
                return web.Response(text="Failed to get access token", status=400)

            user_headers = {"Authorization": f"Bearer {access_token}"}
            async with session.get(
                f"{DISCORD_API_BASE}/users/@me", headers=user_headers
            ) as user_resp:
                user_json = await user_resp.json()

            user_id = int(user_json["id"])
            user = self.bot.get_user(user_id)
            is_owner = await self.bot.is_owner(user)

            if not is_owner:
                return web.Response(
                    text=f"Access denied. You are not a bot owner. User ID: {user_id}",
                    status=403,
                )

            self._authed_users.add(user_id)

            html = f"""
<html>
  <body>
    <script>
      localStorage.setItem('user_id', '{user_id}');
      window.location.href = '/stats.html';
    </script>
    Redirecting to stats...
  </body>
</html>
"""
            return web.Response(text=html, content_type="text/html")

    # === REDBOT CONFIG COMMANDS ===

    @commands.group()
    @commands.is_owner()
    async def webuiconfig(self, ctx):
        """Manage WebUI OAuth settings."""
        pass

    @webuiconfig.command(name="set")
    async def webuiconfig_set(self, ctx, field: str, *, value: str):
        """Set a config field. Usage: [p]webuiconfig set client_id <value>"""
        valid_fields = ["client_id", "client_secret", "redirect_uri"]
        if field not in valid_fields:
            await ctx.send(f"Invalid field. Must be one of: {', '.join(valid_fields)}")
            return

        await getattr(self.config, field).set(value)
        await ctx.send(f"Set `{field}` to `{value}`.")

    @webuiconfig.command(name="show")
    async def webuiconfig_show(self, ctx):
        """Show the current stored OAuth configuration (owner-only)."""
        client_id = await self.config.client_id()
        client_secret = await self.config.client_secret()
        redirect_uri = await self.config.redirect_uri()

        masked_secret = (
            client_secret[:4] + "..." + client_secret[-4:]
            if client_secret and len(client_secret) >= 8
            else "Not Set"
        )

        embed = discord.Embed(
            title="WebUI OAuth Config",
            color=await ctx.embed_color(),
            description="Stored Discord OAuth2 credentials:",
        )
        embed.add_field(name="Client ID", value=client_id or "Not Set", inline=False)
        embed.add_field(name="Client Secret", value=masked_secret, inline=False)
        embed.add_field(name="Redirect URI", value=redirect_uri or "Not Set", inline=False)

        await ctx.send(embed=embed)
