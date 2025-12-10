import discord
from redbot.core import commands, Config


class JoinSoundboard(commands.Cog):
    """Play a soundboard sound when someone joins a voice channel."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xC0FFEE, force_registration=True)
        # Guild-level settings
        self.config.register_guild(
            enabled=False,
            default_sound_id=None,  # default soundboard sound ID for this guild
        )
        # Per-member settings
        self.config.register_member(
            sound_id=None,          # per-member soundboard sound ID
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Ignore bots
        if member.bot:
            return
        # No actual channel change
        if before.channel == after.channel:
            return
        # User left only
        if after.channel is None:
            return

        guild = member.guild
        gconf = await self.config.guild(guild).all()
        if not gconf["enabled"]:
            return

        # Per-user sound first, then default
        mconf = await self.config.member(member).all()
        sound_id_str = mconf["sound_id"] or gconf["default_sound_id"]
        if not sound_id_str:
            return

        # Ensure the bot is in the channel
        vc = guild.voice_client
        if vc is None or not vc.is_connected():
            try:
                vc = await after.channel.connect()
            except discord.ClientException:
                return

        # Parse the stored sound ID
        try:
            sound_id = int(sound_id_str)
        except ValueError:
            return

        # This should call whatever helper your discord.py/Red build exposes
        # for the Soundboard "send sound" endpoint:
        # POST /channels/{channel.id}/send-soundboard-sound
        await guild.play_soundboard_sound(
            sound_id=sound_id,
            channel=after.channel,
        )

    # =====================
    # Configuration commands
    # =====================

    @commands.admin_or_permissions(manage_guild=True)
    @commands.group(name="joinsb", invoke_without_command=True)
    async def joinsb(self, ctx):
        """Configure join soundboard playback."""
        gconf = await self.config.guild(ctx.guild).all()
        await ctx.send(
            f"Enabled: {gconf['enabled']}\n"
            f"Default sound ID: {gconf['default_sound_id']}"
        )

    @joinsb.command(name="enable")
    async def joinsb_enable(self, ctx, enabled: bool):
        """Enable or disable join sounds."""
        await self.config.guild(ctx.guild).enabled.set(enabled)
        await ctx.send(f"Join soundboard is now set to: {enabled}")

    @joinsb.command(name="default")
    async def joinsb_default(self, ctx, sound_id: int):
        """Set the default soundboard sound ID for this server."""
        await self.config.guild(ctx.guild).default_sound_id.set(str(sound_id))
        await ctx.send(f"Default join sound set to ID: {sound_id}")

    @joinsb.command(name="user")
    async def joinsb_user(self, ctx, member: discord.Member, sound_id: int):
        """Set a per-user soundboard sound ID."""
        await self.config.member(member).sound_id.set(str(sound_id))
        await ctx.send(f"Join sound for {member.mention} set to ID: {sound_id}")

    @joinsb.command(name="clearuser")
    async def joinsb_clearuser(self, ctx, member: discord.Member):
        """Clear a user's custom sound so they use the default."""
        await self.config.member(member).sound_id.clear()
        await ctx.send(f"Cleared custom join sound for {member.mention}.")
