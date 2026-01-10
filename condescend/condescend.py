import discord
from redbot.core import commands, Config
from openai import AsyncOpenAI

class Condescend(commands.Cog):
    """
    A cog that replies condescendingly when mentioned in a reply.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        
        # Default config structure
        default_global = {
            "api_key": None,
            "model": "gpt-3.5-turbo", # You can change this to gpt-4o if you want to pay more for better insults
            "system_prompt": (
                "You are a highly intelligent but incredibly arrogant and condescending AI assistant. "
                "You are replying to a Discord user. Keep your response short, witty, and biting. "
                "Talk down to them as if they are a small child who just asked a stupid question."
            )
        }
        self.config.register_global(**default_global)
        self.client = None

    async def _init_openai(self):
        """Initializes the OpenAI client if the key exists."""
        api_key = await self.config.api_key()
        if api_key:
            self.client = AsyncOpenAI(api_key=api_key)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, api_tokens):
        """Reloads client if tokens change (optional safety)."""
        if service_name == "openai":
            await self._init_openai()

    @commands.command()
    @commands.is_owner()
    async def setopenai(self, ctx, key: str):
        """Set your OpenAI API key."""
        await self.config.api_key.set(key)
        await self._init_openai()
        await ctx.send("I have saved your API key. Try not to leak it, genius.")
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command()
    @commands.is_owner()
    async def setpersona(self, ctx, *, prompt: str):
        """Change the system prompt/persona."""
        await self.config.system_prompt.set(prompt)
        await ctx.send("Persona updated. I'm sure it's an improvement.")

    @commands.command()
    @commands.is_owner()
    async def setmodel(self, ctx, model_name: str):
        """
        Set the OpenAI model to use.
        Common options: gpt-4o, gpt-4o-mini, gpt-3.5-turbo
        """
        await self.config.model.set(model_name)
        await ctx.send(f"Model changed to `{model_name}`. Let's hope your wallet can handle it.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Ignore yourself and other bots
        if message.author.bot:
            return

        # 2. Check if the message is a REPLY (has a reference)
        if not message.reference:
            return

        # 3. Check if the bot was MENTIONED in the message
        # (This ensures it only triggers when you strictly @ the bot)
        if not self.bot.user.mentioned_in(message):
            return

        # Check if API key is set
        if not self.client:
            # Try to init in case it was set but client is None (first run)
            await self._init_openai()
            if not self.client:
                return 

        # 4. Fetch the message the user is replying TO (context)
        try:
            # We need the original message to give the AI context
            replied_msg = message.reference.resolved
            if not replied_msg:
                # If the message isn't in cache, we might need to fetch it
                channel = self.bot.get_channel(message.channel.id)
                replied_msg = await channel.fetch_message(message.reference.message_id)
                
            original_text = replied_msg.content
            user_text = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return # Fail silently if we can't read the context

        # 5. Send to LLM
        async with message.channel.typing():
            try:
                system_prompt = await self.config.system_prompt()
                model = await self.config.model()

                response = await self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"The user replied to this text: '{original_text}'. The user said: '{user_text}'."}
                    ],
                    max_tokens=150
                )
                
                reply_text = response.choices[0].message.content
                
                # 6. Reply back
                await message.reply(reply_text, mention_author=True)

            except Exception as e:
                # Log error to console, but don't spam chat
                print(f"Error in Condescend cog: {e}")
