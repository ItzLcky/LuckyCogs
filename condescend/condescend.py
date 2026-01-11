import discord
from redbot.core import commands, Config
from openai import AsyncOpenAI

class Condescend(commands.Cog):
    """
    A cog that replies condescendingly when mentioned, supporting OpenAI or Ollama.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        
        # Global settings
        default_global = {
            "api_key": None,
            "base_url": None, # New: Custom URL support
            "model": "gpt-3.5-turbo",
            "system_prompt": (
                "You are a highly intelligent but incredibly arrogant and condescending AI assistant. "
                "You are replying to a Discord user. Keep your response short, witty, and biting. "
                "Talk down to them as if they are a small child who just asked a stupid question."
            )
        }
        self.config.register_global(**default_global)
        
        # Channel-specific history
        default_channel = {
            "history": []
        }
        self.config.register_channel(**default_channel)

        self.client = None

    async def _init_openai(self):
        """Initializes the Client with custom URL or OpenAI defaults."""
        api_key = await self.config.api_key()
        base_url = await self.config.base_url()

        # If using Ollama/Local, we often don't need a real key, but the library requires one.
        if base_url and not api_key:
            api_key = "ollama" 

        if api_key:
            if base_url:
                self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            else:
                self.client = AsyncOpenAI(api_key=api_key)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, api_tokens):
        if service_name == "openai":
            await self._init_openai()

    @commands.command()
    @commands.is_owner()
    async def setopenai(self, ctx, key: str):
        """Set your OpenAI API key (Not needed for local Ollama)."""
        await self.config.api_key.set(key)
        await self._init_openai()
        await ctx.send("API key updated.")
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command()
    @commands.is_owner()
    async def seturl(self, ctx, url: str = None):
        """
        Set a custom API URL (e.g., for Ollama).
        Usage: [p]seturl http://localhost:11434/v1
        Reset: [p]seturl clear
        """
        if url and url.lower() == "clear":
            await self.config.base_url.set(None)
            await self._init_openai()
            await ctx.send("Custom URL cleared. Reverting to OpenAI standard.")
            return

        await self.config.base_url.set(url)
        await self._init_openai()
        await ctx.send(f"Endpoint URL set to `{url}`.")

    @commands.command()
    @commands.is_owner()
    async def setpersona(self, ctx, *, prompt: str):
        """Change the system prompt/persona."""
        await self.config.system_prompt.set(prompt)
        await ctx.send("Persona updated.")

    @commands.command()
    @commands.is_owner()
    async def setmodel(self, ctx, model_name: str):
        """
        Set the model name.
        OpenAI: gpt-4o, gpt-3.5-turbo
        Ollama: llama3, mistral, deepseek-coder
        """
        await self.config.model.set(model_name)
        await ctx.send(f"Model changed to `{model_name}`.")

    @commands.command()
    @commands.admin_or_permissions(manage_messages=True)
    async def forget(self, ctx):
        """Wipes the bot's memory for this channel."""
        await self.config.channel(ctx.channel).history.set([])
        await ctx.send("Memory wiped.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not self.bot.user.mentioned_in(message):
            return

        # Initialize if needed
        if not self.client:
            await self._init_openai()
            if not self.client:
                return 

        # Fetch Context
        try:
            my_author = message.author.display_name
            user_text = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
            
            current_interaction_text = ""
            
            if message.reference:
                # Reply Scenario
                replied_msg = message.reference.resolved
                if not replied_msg:
                    channel = self.bot.get_channel(message.channel.id)
                    replied_msg = await channel.fetch_message(message.reference.message_id)
                
                original_author = replied_msg.author.display_name
                original_text = replied_msg.content
                
                current_interaction_text = (
                    f"CONTEXT: User '{original_author}' said: \"{original_text}\"\n"
                    f"User '{my_author}' (replying to them) said to YOU: \"{user_text}\"\n"
                )
            else:
                # Direct Mention Scenario
                current_interaction_text = (
                    f"User '{my_author}' said to YOU: \"{user_text}\"\n"
                )
            
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return 

        async with message.channel.typing():
            try:
                system_prompt = await self.config.system_prompt()
                model = await self.config.model()
                history = await self.config.channel(message.channel).history()
                
                messages_payload = []
                
                # Check for OpenAI o1 models (Ollama doesn't use this usually)
                is_o1 = model.startswith("o1")
                token_arg_name = "max_completion_tokens" if is_o1 else "max_tokens"

                if is_o1:
                    history_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
                    full_content = (
                        f"{system_prompt}\n\n"
                        f"--- PREVIOUS CONVERSATION HISTORY ---\n{history_text}\n"
                        f"--- CURRENT INTERACTION ---\n{current_interaction_text}\n"
                        f"INSTRUCTION: Reply to '{my_author}'."
                    )
                    messages_payload.append({"role": "user", "content": full_content})
                else:
                    messages_payload.append({"role": "system", "content": system_prompt})
                    for msg in history:
                        messages_payload.append(msg)
                    messages_payload.append({"role": "user", "content": current_interaction_text})

                api_args = {
                    "model": model,
                    "messages": messages_payload,
                    token_arg_name: 300
                }

                response = await self.client.chat.completions.create(**api_args)
                reply_text = response.choices[0].message.content
                
                await message.reply(reply_text, mention_author=True)

                # Save Memory
                new_history_entries = [
                    {"role": "user", "content": current_interaction_text},
                    {"role": "assistant", "content": reply_text}
                ]
                history.extend(new_history_entries)
                
                if len(history) > 6: 
                    history = history[-6:]
                
                await self.config.channel(message.channel).history.set(history)

            except Exception as e:
                await message.reply(f"❌ **Error:** {str(e)}", mention_author=True)
                print(f"Error in Condescend cog: {e}")
