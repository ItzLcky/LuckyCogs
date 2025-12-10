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
            default_sound_id=None,
        )
        # Per-member settings
        self.config.register_member(
            sound_id=None,
        )
        # Track which guilds are currently playing sounds
        self.playing_guilds = set()
    
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
        
        # Prevent multiple simultaneous plays in the same guild
        if guild.id in self.playing_guilds:
            return
        
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
        
        # Mark this guild as currently playing
        self.playing_guilds.add(guild.id)
        
        try:
            # Try to send soundboard sound WITHOUT connecting to voice
            # This may work if the API allows it
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
            print(f"✅ Played sound {sound_id} for {member.name} in {after.channel.name}")
            
            # Small cooldown before allowing next sound
            await asyncio.sleep(2)
            
        except discord.HTTPException as e:
            print(f"❌ HTTP Error {e.status}: {e.text}")
            # If we get a 403 about needing to be in voice, we know we need voice connection
            if "must be in voice channel" in str(e).lower():
                print("⚠️ Bot needs to be in voice channel. Checking firewall/network settings.")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
        finally:
            self.playing_guilds.discard(guild.id)
    
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
