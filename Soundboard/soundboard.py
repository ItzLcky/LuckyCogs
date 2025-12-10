import re
from pathlib import Path

import discord
import yt_dlp
from redbot.core import commands, Config, data_manager


class SoundBoard(commands.Cog):
    """Soundboard cog with local files and YouTube imports."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x53424F41)  # SBOA
        # Directory to store sounds
        self.sounds_path: Path = data_manager.cog_data_path(cog_instance=self) / "sounds"
        self.sounds_path.mkdir(parents=True, exist_ok=True)

    # ------------- helpers -------------

    async def _get_sounds(self):
        exts = (".mp3", ".wav", ".ogg", ".flac", ".m4a")
        return sorted(
            p for p in self.sounds_path.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        )

    async def _ensure_connected(self, ctx: commands.Context) -> discord.VoiceClient:
        """Join or move to the author's voice channel."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.UserFeedbackCheckFailure("You must be in a voice channel.")

        channel = ctx.author.voice.channel
        vc: discord.VoiceClient | None = getattr(ctx.guild, "voice_client", None)

        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
        else:
            vc = await channel.connect()

        return vc

    def _sanitize_filename(self, title: str) -> str:
        """Sanitize YouTube titles into safe filenames."""
        safe = re.sub(r"[^A-Za-z0-9 _\-]+", "", title)
        safe = safe.strip().replace(" ", "_")
        return safe or "sound"

    # ------------- soundboard commands -------------

    @commands.command(name="soundboard")
    async def soundboard_list(self, ctx: commands.Context):
        """List available sounds."""
        sounds = await self._get_sounds()
        if not sounds:
            await ctx.send("No sounds found. Put audio files into the soundboard data folder.")
            return

        names = [p.stem for p in sounds]
        await ctx.send("Available sounds:\n" + ", ".join(sorted(names)))

    @commands.command(name="playsound")
    async def play_sound(self, ctx: commands.Context, *, name: str):
        """Play a sound by name (based on filename)."""
        sounds = await self._get_sounds()
        if not sounds:
            await ctx.send("No sounds found. Put audio files into the soundboard data folder.")
            return

        match = None
        lname = name.lower()
        for p in sounds:
            if p.stem.lower() == lname:
                match = p
                break

        if not match:
            await ctx.send("Sound not found. Use `[p]soundboard` to see available names.")
            return

        try:
            vc = await self._ensure_connected(ctx)
        except commands.UserFeedbackCheckFailure as e:
            await ctx.send(str(e))
            return

        if vc.is_playing():
            vc.stop()

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(str(match))
        )
        vc.play(source)

        await ctx.send(f"Playing `{match.stem}` in {vc.channel.mention}.")

    @commands.command(name="stopsound")
    async def stop_sound(self, ctx: commands.Context):
        """Stop the currently playing sound."""
        vc: discord.VoiceClient | None = getattr(ctx.guild, "voice_client", None)
        if not vc or not vc.is_connected():
            await ctx.send("Not connected to a voice channel.")
            return
        if vc.is_playing():
            vc.stop()
            await ctx.send("Stopped playback.")
        else:
            await ctx.send("Nothing is playing.")

    # ------------- YouTube download -------------

    @commands.command(name="ytdlsound")
    @commands.is_owner()
    async def ytdl_sound(self, ctx: commands.Context, url: str):
        """Download YouTube audio into the soundboard.

        Owner-only. Downloads best audio, converts to mp3, and stores in the sounds folder.
        The resulting sound name is the sanitized video title.
        """
        await ctx.trigger_typing()

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(self.sounds_path / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info.get("title", "sound")

        try:
            title = await self.bot.loop.run_in_executor(None, _download)
        except Exception as e:
            await ctx.send(f"Download failed: `{e}`")
            return

        safe_title = self._sanitize_filename(title)

        # Find the downloaded mp3 (with original title) and rename/sanitize.
        found = False
        for p in self.sounds_path.glob("*.mp3"):
            if p.stem == title:
                new_path = self.sounds_path / f"{safe_title}.mp3"
                if p != new_path:
                    p.rename(new_path)
                found = True
                break

        if not found:
            await ctx.send("Download finished but the file could not be located.")
            return

        await ctx.send(
            "Added sound `{}` from YouTube. Use `[p]playsound {}`.".format(
                safe_title, safe_title
            )
        )


def setup(bot):
    bot.add_cog(SoundBoard(bot))
