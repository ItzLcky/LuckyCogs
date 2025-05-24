# webui.py (corrected)

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.cogs.customcom import CustomCommands
import discord

log = logging.getLogger("red.WebUI")

DISCORD_API_BASE = "https://discord.com/api"

class WebUI(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self._runner = None
        self._site = None
        self.config = Config.get_conf(self, identifier=6543210)
        default_global = {
            "client_id": None,
            "client_secret": None,
            "redirect_uri": "http://localhost:8080/oauth/callback",
            "port": 5050,
        }
        self.config.register_global(**default_global)
        self._authed_users = set()
        self._message_counts = {}
        bot.loop.create_task(self.start_server())

    async def start_server(self):
        await self.bot.wait_until_ready()
        self._port = await self.config.port()
        app = web.Application()

        app.router.add_get("/api/ping", self.handle_ping)
        app.router.add_get("/api/user/{user_id}", self.handle_get_user)
        app.router.add_get("/api/guilds", self.handle_get_guilds)
        app.router.add_get("/api/guild/{guild_id}", self.handle_guild_details)
        app.router.add_get("/api/guild/{guild_id}/ccs", self.handle_list_ccs)
        app.router.add_post("/api/guild/{guild_id}/ccs", self.handle_edit_cc)
        app.router.add_delete("/api/guild/{guild_id}/ccs/{cmd_name}", self.handle_delete_cc)
        app.router.add_get("/api/stats", self.handle_stats)

        app.router.add_get("/admin", self.handle_admin_page)
        app.router.add_get("/oauth/login", self.handle_oauth_login)
        app.router.add_get("/oauth/callback", self.handle_oauth_callback)

        static_path = Path(__file__).parent / "static"
        if static_path.exists():
            app.router.add_static("/", static_path, show_index=True)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        try:
            await self._site.start()
            log.info(f"WebUI is running on port {self._port}")
        except Exception as e:
            log.exception("Failed to start WebUI server")

    async def cog_unload(self):
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild and not message.author.bot:
            gid = message.guild.id
            self._message_counts[gid] = self._message_counts.get(gid, 0) + 1

    async def handle_ping(self, request):
        return web.json_response({"status": "ok", "message": "pong"})

    async def handle_get_user(self, request):
        user_id = int(request.match_info["user_id"])
        user = self.bot.get_user(user_id)
        if user:
            return web.json_response({
                "id": user.id,
                "name": str(user),
                "avatar": str(user.avatar_url) if hasattr(user, "avatar_url") else None,
            })
        return web.json_response({"error": "User not found"}, status=404)

    async def handle_get_guilds(self, request):
        user_id = int(request.headers.get("X-User-ID", 0))
        if user_id not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)
        return web.json_response({
            "guilds": [ {
                "id": str(g.id),
                "name": g.name,
                "member_count": g.member_count
            } for g in self.bot.guilds ]
        })

    async def handle_guild_details(self, request):
        user_id = int(request.headers.get("X-User-ID", 0))
        if user_id not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)

        guild_id = int(request.match_info["guild_id"])
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Guild not found"}, status=404)

        return web.json_response({
            "id": str(guild.id),
            "name": guild.name,
            "member_count": guild.member_count,
            "message_count": self._message_counts.get(guild.id, 0)
        })

    async def handle_stats(self, request):
        user_id = int(request.headers.get("X-User-ID", 0))
        if user_id not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)

        return web.json_response({
            "total_guilds": len(self.bot.guilds),
            "total_users": sum(g.member_count for g in self.bot.guilds),
            "cogs_loaded": list(self.bot.cogs.keys())
        })

    async def handle_list_ccs(self, request):
        user_id = int(request.headers.get("X-User-ID", 0))
        if user_id not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)

        guild_id = int(request.match_info["guild_id"])
        cog: CustomCommands = self.bot.get_cog("CustomCommands")
        if not cog:
            return web.json_response({"error": "CustomCommands cog not loaded"}, status=500)

        commands = await cog.config.guild_from_id(guild_id).commands()
        return web.json_response({k.lower(): v for k, v in commands.items()})

    async def handle_edit_cc(self, request):
        user_id = int(request.headers.get("X-User-ID", 0))
        if user_id not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)

        guild_id = int(request.match_info["guild_id"])
        data = await request.json()
        name = data.get("name", "").strip().lower()
        response = data.get("response", "").strip()

        if not name or not response:
            return web.json_response({"error": "Missing fields"}, status=400)

        cog: CustomCommands = self.bot.get_cog("CustomCommands")
        cmds = await cog.config.guild_from_id(guild_id).commands()
        cmds[name] = {"response": response}
        await cog.config.guild_from_id(guild_id).commands.set(cmds)
        return web.json_response({"status": "success", "updated": name})

    async def handle_delete_cc(self, request):
        user_id = int(request.headers.get("X-User-ID", 0))
        if user_id not in self._authed_users:
            return web.json_response({"error": "Unauthorized"}, status=403)

        guild_id = int(request.match_info["guild_id"])
        cmd_name = request.match_info["cmd_name"].lower()
        cog: CustomCommands = self.bot.get_cog("CustomCommands")
        cmds = await cog.config.guild_from_id(guild_id).commands()
        if cmd_name in cmds:
            del cmds[cmd_name]
            await cog.config.guild_from_id(guild_id).commands.set(cmds)
            return web.json_response({"status": "deleted", "command": cmd_name})
        return web.json_response({"error": "Command not found"}, status=404)

    async def handle_admin_page(self, request):
        html_path = Path(__file__).parent / "static" / "admin.html"
        if html_path.exists():
            return web.FileResponse(html_path)
        return web.Response(text="Admin page not found", status=404)

    async def handle_oauth_login(self, request):
        client_id = await self.config.client_id()
        redirect_uri = await self.config.redirect_uri()
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
        client_id = await self.config.client_id()
        client_secret = await self.config.client_secret()
        redirect_uri = await self.config.redirect_uri()

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
            async with session.post(f"{DISCORD_API_BASE}/oauth2/token", data=token_data, headers=headers) as token_resp:
                token_json = await token_resp.json()
                access_token = token_json.get("access_token")

            user_headers = {"Authorization": f"Bearer {access_token}"}
            async with session.get(f"{DISCORD_API_BASE}/users/@me", headers=user_headers) as user_resp:
                user_json = await user_resp.json()

            user_id = int(user_json["id"])
            user = self.bot.get_user(user_id)
            is_owner = await self.bot.is_owner(user)
            if not is_owner:
                return web.Response(text="Access denied", status=403)

            self._authed_users.add(user_id)
            html = f"""
            <html><body><script>
              localStorage.setItem('user_id', '{user_id}');
              window.location.href = '/stats.html';
            </script>Logging in...</body></html>"""
            return web.Response(text=html, content_type="text/html")

    @commands.group()
    @commands.is_owner()
    async def webuiconfig(self, ctx):
        """Manage WebUI OAuth and port settings."""
        pass

    @webuiconfig.command(name="set")
    async def webuiconfig_set(self, ctx, field: str, *, value: str):
        valid_fields = ["client_id", "client_secret", "redirect_uri", "port"]
        if field not in valid_fields:
            await ctx.send(f"Invalid field. Choose from: {', '.join(valid_fields)}")
            return
        if field == "port":
            try:
                value = int(value)
            except ValueError:
                await ctx.send("Port must be a number.")
                return
        await getattr(self.config, field).set(value)
        await ctx.send(f"Set `{field}` to `{value}`. Please restart the bot for changes to apply.")

    @webuiconfig.command(name="show")
    async def webuiconfig_show(self, ctx):
        client_id = await self.config.client_id()
        client_secret = await self.config.client_secret()
        redirect_uri = await self.config.redirect_uri()
        port = await self.config.port()
        masked = (
            client_secret[:4] + "..." + client_secret[-4:]
            if client_secret and len(client_secret) > 8 else "Not Set"
        )
        embed = discord.Embed(title="WebUI Config", color=await ctx.embed_color())
        embed.add_field(name="Client ID", value=client_id or "Not Set", inline=False)
        embed.add_field(name="Client Secret", value=masked, inline=False)
        embed.add_field(name="Redirect URI", value=redirect_uri or "Not Set", inline=False)
        embed.add_field(name="Port", value=str(port), inline=False)
        await ctx.send(embed=embed)
