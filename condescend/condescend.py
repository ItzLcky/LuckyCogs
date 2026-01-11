import discord
from redbot.core import commands, Config
from openai import AsyncOpenAI
import google.generativeai as genai

class Condescend(commands.Cog):
    """
    A cog that replies condescendingly, supporting OpenAI (ChatGPT/Ollama) and Google (Gemini).
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        
        default_global = {
            "provider": "openai",     # Options: "openai" or "google"
            "api_key": None,          # OpenAI/Ollama Key
            "gemini_key": None,       # Google Gemini Key
            "base_url": None,         # For Ollama
            "model": "gpt-3.5-turbo", # Default OpenAI model
            "gemini_model": "gemini-1.5-flash", # Default Gemini model
            "system_prompt": (
                "You are a highly intelligent but incredibly arrogant and condescending AI assistant. "
                "You are replying to a Discord user. Keep your response short, witty, and biting. "
                "Talk down to them as if they are a small child who just asked a stupid question."
            )
        }
        self.config.register_global(**default_global)
        
        default_channel = {
            "history": []
        }
        self.config.register_channel(**default_channel)

        self.client = None # OpenAI Client

    async def _init_openai(self):
        """Initializes the OpenAI client."""
        api_key = await self.config.api_key()
        base_url = await self.config.base_url()
        
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

    # --- CONFIGURATION COMMANDS ---

    @commands.command()
    @commands.is_owner()
    async def setprovider(self, ctx, provider: str):
        """
        Set the AI provider.
        Options: 'openai' (ChatGPT/Ollama) or 'google' (Gemini).
        """
        if provider.lower() not in ["openai", "google"]:
            await ctx.send("Invalid provider. Please choose `openai` or `google`.")
            return
        
        await self.config.provider.set(provider.lower())
        await ctx.send(f"Provider switched to **{provider.upper()}**.")

    @commands.command()
    @commands.is_owner()
    async def setopenai(self, ctx, key: str):
        """Set OpenAI API key."""
        await self.config.api_key.set(key)
        await self._init_openai()
        await ctx.send("OpenAI key updated.")
        try:
            await ctx.message.delete()
        except: pass

    @commands.command()
    @commands.is_owner()
    async def setgemini(self, ctx, key: str):
        """Set Google Gemini API key."""
        await self.config.gemini_key.set(key)
        await ctx.send("Gemini key updated.")
        try:
            await ctx.message.delete()
        except: pass

    @commands.command()
    @commands.is_owner()
    async def seturl(self, ctx, url: str = None):
        """Set custom URL for Ollama (used only if provider is 'openai')."""
        if url and url.lower() == "clear":
            await self.config.base_url.set(None)
            await self._init_openai()
            await ctx.send("Custom URL cleared.")
            return
        await self.config.base_url.set(url)
        await self._init_openai()
        await ctx.send(f"Endpoint URL set to `{url}`.")

    @commands.command()
    @commands.is_owner()
    async def setpersona(self, ctx, *, prompt: str):
        """Update the system persona."""
        await self.config.system_prompt.set(prompt)
        await ctx.send("Persona updated.")

    @commands.command()
    @commands.is_owner()
    async def setmodel(self, ctx, model_name: str):
        """
        Set the model name (updates whichever provider is currently active).
        """
        provider = await self.config.provider()
        if provider == "google":
            await self.config.gemini_model.set(model_name)
            await ctx.send(f"Gemini model set to `{model_name}`.")
        else:
            await self.config.model.set(model_name)
            await ctx.send(f"OpenAI/Ollama model set to `{model_name}`.")

    @commands.command()
    @commands.admin_or_permissions(manage_messages=True)
    async def forget(self, ctx):
        """Wipes memory."""
        await self.config.channel(ctx.channel).history.set([])
        await ctx.send("Memory wiped.")

    # --- MAIN LOGIC ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        # Prepare Context
        try:
            my_author = message.author.display_name
            user_text = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
            
            if message.reference:
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
                current_interaction_text = (
                    f"User '{my_author}' said to YOU: \"{user_text}\"\n"
                )
        except:
            return 

        async with message.channel.typing():
            try:
                provider = await self.config.provider()
                system_prompt = await self.config.system_prompt()
                history = await self.config.channel(message.channel).history()
                reply_text = ""

                # --- GOOGLE GEMINI LOGIC ---
                if provider == "google":
                    api_key = await self.config.gemini_key()
                    if not api_key:
                        await message.reply("❌ Gemini API Key not set. Use `[p]setgemini`.")
                        return

                    model_name = await self.config.gemini_model()
                    genai.configure(api_key=api_key)
                    
                    # Gemini System Prompt
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_prompt
                    )

                    # Convert History to Gemini Format (user/model)
                    gemini_history = []
                    for msg in history:
                        role = "user" if msg['role'] == "user" else "model"
                        gemini_history.append({"role": role, "parts": [msg['content']]})

                    chat = model.start_chat(history=gemini_history)
                    response = await chat.send_message_async(current_interaction_text)
                    reply_text = response.text

                # --- OPENAI / OLLAMA LOGIC ---
                else:
                    if not self.client:
                        await self._init_openai()
                        if not self.client: return

                    model = await self.config.model()
                    messages_payload = []
                    
                    # OpenAI Formatting
                    is_o1 = model.startswith("o1")
                    token_arg_name = "max_completion_tokens" if is_o1 else "max_tokens"

                    if is_o1:
                        history_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
                        full_content = (
                            f"{system_prompt}\n\n--- PREVIOUS HISTORY ---\n{history_text}\n"
                            f"--- CURRENT ---\n{current_interaction_text}\nINSTRUCTION: Reply to '{my_author}'."
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

                # --- SEND & SAVE ---
                await message.reply(reply_text, mention_author=True)

                new_history_entries = [
                    {"role": "user", "content": current_interaction_text},
                    {"role": "assistant", "content": reply_text}
                ]
                history.extend(new_history_entries)
                if len(history) > 6: history = history[-6:]
                await self.config.channel(message.channel).history.set(history)

            except Exception as e:
                await message.reply(f"❌ **Error:** {str(e)}", mention_author=True)
                print(f"Error: {e}")
