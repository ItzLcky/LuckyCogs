import discord
from discord.ext import commands, tasks
from redbot.core import commands as red_commands, Config
import asyncio
from typing import Optional

class JoinSoundboard(red_commands.Cog):
    """Play soundboard sounds when users join voice channels."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        # Default settings
        default_guild = {
            "enabled": False,
            "default_sound": None,
            "disconnect_delay": 5,  # seconds to wait before disconnecting
        }
        
        default_member = {
            "custom_sound": None,
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        
        # Track active connections
        self.active_plays = {}  # guild_id: asyncio.Task
    
    def cog_unload(self):
        """Cleanup when cog unloads."""
        for task in self.active_plays.values():
            if not task.done():
                task.cancel()
    
    @red_commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Triggered when someone's voice state changes."""
        
        # Skip bots
        if member.bot:
            return
        
        # Only trigger on joins (not leaves or channel switches from same guild perspective)
        if after.channel is None:  # They left
            return
        
        if before.channel == after.channel:  # No change
            return
        
        # Get settings
        guild = member.guild
        is_enabled = await self.config.guild(guild).enabled()
        
        if not is_enabled:
            return
        
        # Get sound ID
        custom_sound = await self.config.member(member).custom_sound()
        default_sound = await self.config.guild(guild).default_sound()
        
        sound_id = custom_sound or default_sound
        
        if sound_id is None:
            return
        
        # Cancel any existing play task for this guild
        if guild.id in self.active_plays:
            old_task = self.active_plays[guild.id]
            if not old_task.done():
                old_task.cancel()
                try:
                    await old_task
                except asyncio.CancelledError:
                    pass
        
        # Create new play task
        task = asyncio.create_task(self._play_sound(after.channel, sound_id, member))
        self.active_plays[guild.id] = task
    
    async def _play_sound(self, channel: discord.VoiceChannel, sound_id: int, trigger_member: discord.Member):
        """Connect to voice, play sound, and disconnect."""
        voice_client: Optional[discord.VoiceClient] = None
        guild = channel.guild
        
        try:
            # Get or create voice connection
            voice_client = guild.voice_client
            
            if voice_client is None:
                # Not connected, connect now
                print(f"[JoinSB] Connecting to {channel.name} in {guild.name}")
                voice_client = await channel.connect(timeout=15.0)
            elif voice_client.channel.id != channel.id:
                # Connected to different channel, move
                print(f"[JoinSB] Moving to {channel.name} in {guild.name}")
                await voice_client.move_to(channel)
            
            # Wait for full connection
            await asyncio.sleep(2)
            
            # Verify connection is ready
            if not voice_client.is_connected():
                print(f"[JoinSB] Failed to establish connection to {channel.name}")
                return
            
            # Play the soundboard sound via API
            print(f"[JoinSB] Playing sound {sound_id} for {trigger_member.name}")
            
            try:
                await self.bot.http.request(
                    discord.http.Route(
                        'POST',
                        '/channels/{channel_id}/send-soundboard-sound',
                        channel_id=channel.id
                    ),
                    json={
                        'sound_id': str(sound_id),
                        'source_guild_id': str(guild.id)
                    }
                )
                print(f"[JoinSB] ✅ Successfully played sound")
            except discord.HTTPException as http_err:
                print(f"[JoinSB] ❌ HTTP Error: {http_err.status} - {http_err.text}")
                return
            
            # Wait for sound to finish
            disconnect_delay = await self.config.guild(guild).disconnect_delay()
            await asyncio.sleep(disconnect_delay)
            
        except asyncio.CancelledError:
            print(f"[JoinSB] Play cancelled for {guild.name}")
            raise
        except Exception as e:
            print(f"[JoinSB] ❌ Error: {type(e).__name__}: {e}")
        finally:
            # Disconnect
            if voice_client and voice_client.is_connected():
                try:
                    await voice_client.disconnect(force=False)
                    print(f"[JoinSB] Disconnected from {guild.name}")
                except:
                    pass
            
            # Cleanup task tracking
            if guild.id in self.active_plays:
                del self.active_plays[guild.id]
    
    # ==================== COMMANDS ====================
    
    @red_commands.group(name="joinsound")
    @red_commands.admin_or_permissions(manage_guild=True)
    async def joinsound(self, ctx):
        """Manage join soundboard settings."""
        if ctx.invoked_subcommand is None:
            # Show current settings
            enabled = await self.config.guild(ctx.guild).enabled()
            default_sound = await self.config.guild(ctx.guild).default_sound()
            delay = await self.config.guild(ctx.guild).disconnect_delay()
            
            embed = discord.Embed(
                title="Join Soundboard Settings",
                color=discord.Color.blue()
            )
            embed.add_field(name="Enabled", value=str(enabled), inline=True)
            embed.add_field(name="Default Sound ID", value=str(default_sound) if default_sound else "None", inline=True)
            embed.add_field(name="Disconnect Delay", value=f"{delay}s", inline=True)
            
            await ctx.send(embed=embed)
    
    @joinsound.command(name="enable")
    async def joinsound_enable(self, ctx, enabled: bool):
        """Enable or disable the join soundboard feature."""
        await self.config.guild(ctx.guild).enabled.set(enabled)
        await ctx.send(f"✅ Join soundboard {'enabled' if enabled else 'disabled'}.")
    
    @joinsound.command(name="setdefault")
    async def joinsound_setdefault(self, ctx, sound_id: int):
        """Set the default soundboard sound ID for all users."""
        await self.config.guild(ctx.guild).default_sound.set(sound_id)
        await ctx.send(f"✅ Default join sound set to ID: `{sound_id}`")
    
    @joinsound.command(name="cleardefault")
    async def joinsound_cleardefault(self, ctx):
        """Clear the default soundboard sound."""
        await self.config.guild(ctx.guild).default_sound.set(None)
        await ctx.send("✅ Default sound cleared.")
    
    @joinsound.command(name="setuser")
    async def joinsound_setuser(self, ctx, member: discord.Member, sound_id: int):
        """Set a custom soundboard sound for a specific user."""
        await self.config.member(member).custom_sound.set(sound_id)
        await ctx.send(f"✅ Custom join sound for {member.mention} set to ID: `{sound_id}`")
    
    @joinsound.command(name="clearuser")
    async def joinsound_clearuser(self, ctx, member: discord.Member):
        """Clear a user's custom soundboard sound."""
        await self.config.member(member).custom_sound.set(None)
        await ctx.send(f"✅ Custom sound cleared for {member.mention}. They will use the default sound.")
    
    @joinsound.command(name="delay")
    async def joinsound_delay(self, ctx, seconds: int):
        """Set how long the bot waits before disconnecting (1-30 seconds)."""
        if seconds < 1 or seconds > 30:
            await ctx.send("❌ Delay must be between 1 and 30 seconds.")
            return
        
        await self.config.guild(ctx.guild).disconnect_delay.set(seconds)
        await ctx.send(f"✅ Disconnect delay set to {seconds} seconds.")
    
    @joinsound.command(name="test")
    async def joinsound_test(self, ctx, sound_id: Optional[int] = None):
        """Test the soundboard by playing a sound in your current voice channel."""
        
        # Check if user is in voice
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You must be in a voice channel to test.")
            return
        
        # Get sound ID
        if sound_id is None:
            sound_id = await self.config.guild(ctx.guild).default_sound()
            if sound_id is None:
                await ctx.send("❌ No sound ID provided and no default sound set.")
                return
        
        channel = ctx.author.voice.channel
        
        await ctx.send(f"🔊 Testing sound ID `{sound_id}` in {channel.mention}...")
        
        # Use the same play logic
        task = asyncio.create_task(self._play_sound(channel, sound_id, ctx.author))
        
        try:
            await task
            await ctx.send("✅ Test complete!")
        except Exception as e:
            await ctx.send(f"❌ Test failed: {e}")


def setup(bot):
    """Required for Red-DiscordBot cog loading."""
    bot.add_cog(JoinSoundboard(bot))
