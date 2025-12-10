import discord
import asyncio
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
        
        # Parse the stored sound ID
        try:
            sound_id = int(sound_id_str)
        except ValueError:
            print(f"Invalid sound ID: {sound_id_str}")
            return
        
        # Check if bot is already in a voice channel in this guild
        vc = guild.voice_client
        
        # If bot is in a different channel, move it
        if vc and vc.channel != after.channel:
            try:
                await vc.move_to(after.channel)
            except Exception as e:
                print(f"Failed to move to channel: {e}")
                return
        # If bot is not connected at all, connect
        elif vc is None:
            try:
                vc = await after.channel.connect(timeout=30.0, reconnect=True)
            except Exception as e:
                print(f"Failed to connect to voice channel: {e}")
                return
        
        # Wait for connection to stabilize
        await asyncio.sleep(1)
        
        # Play soundboard sound using HTTP API
        try:
            await self.bot.http.request(
                discord.http.Route(
                    'POST',
                    '/channels/{channel_id}/send-soundboard-sound',
                    channel_id=after.channel.id
                ),
                json={
                    'sound_id': str(sound_id),
                    'source_guild_id': str(guild.id)
                }
            )
            print(f"Played sound {sound_id} for {member.name} in {after.channel.name}")
            
            # Wait for sound to finish (adjust time based on your sound length)
            await asyncio.sleep(3)
            
            # Disconnect after playing
            if vc and vc.is_connected():
                await vc.disconnect()
                
        except discord.HTTPException as e:
            print(f"Failed to play soundboard sound: {e}")
            if vc and vc.is_connected():
                await vc.disconnect()
        except Exception as e:
            print(f"Unexpected error playing sound: {e}")
            if vc and vc.is_connected():
                await vc.disconnect()
    
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
    
    @joinsb.command(name="test")
    async def joinsb_test(self, ctx):
        """Test if the bot can connect to your current voice channel."""
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel!")
            return
        
        channel = ctx.author.voice.channel
        
        # Check permissions
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.connect:
            await ctx.send("❌ Bot doesn't have CONNECT permission!")
            return
        if not permissions.speak:
            await ctx.send("❌ Bot doesn't have SPEAK permission!")
            return
        
        try:
            await ctx.send(f"Attempting to connect to {channel.mention}...")
            vc = await channel.connect(timeout=30.0, reconnect=True)
            await ctx.send(f"✅ Successfully connected to {channel.mention}")
            await asyncio.sleep(2)
            await vc.disconnect()
            await ctx.send("✅ Disconnected successfully")
        except Exception as e:
            import traceback
            error_details = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            await ctx.send(f"❌ Failed to connect: {type(e).__name__}: {e}")
            print(f"Full error:\n{error_details}")
