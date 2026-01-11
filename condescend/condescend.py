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

    @commands.command()
    @commands.admin_or_permissions(manage_messages=True)
    async def forget(self, ctx):
        """Wipes the bot's memory for this channel."""
        await self.config.channel(ctx.channel).history.set([])
        await ctx.send("I have wiped my memory of this channel. Consider yourselves lucky.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.reference or not self.bot.user.mentioned_in(message):
            return

        if not self.client:
            await self._init_openai()
            if not self.client:
                return 

        try:
            # Fetch context
            replied_msg = message.reference.resolved
            if not replied_msg:
                channel = self.bot.get_channel(message.channel.id)
                replied_msg = await channel.fetch_message(message.reference.message_id)
            
            original_author = replied_msg.author.display_name
            original_text = replied_msg.content
            my_author = message.author.display_name
            user_text = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
            
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return 

        async with message.channel.typing():
            try:
                system_prompt = await self.config.system_prompt()
                model = await self.config.model()
                
                # --- MEMORY LOGIC START ---
                # 1. Get recent history for this channel
                history = await self.config.channel(message.channel).history()
                
                # 2. Define the current interaction
                current_interaction_text = (
                    f"User '{original_author}' said: \"{original_text}\"\n"
                    f"User '{my_author}' replied: \"{user_text}\"\n"
                )
                
                # 3. Construct the message payload
                messages_payload = []
                
                # Check for o1 model specific formatting
                is_o1 = model.startswith("o1")
                token_arg_name = "max_completion_tokens" if is_o1 else "max_tokens"

                if is_o1:
                    # For o1, we flatten history into one big prompt because it handles 'roles' poorly
                    history_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
                    full_content = (
                        f"{system_prompt}\n\n"
                        f"--- PREVIOUS CONVERSATION HISTORY ---\n{history_text}\n"
                        f"--- CURRENT INTERACTION ---\n{current_interaction_text}\n"
                        f"INSTRUCTION: Reply to '{my_author}'."
                    )
                    messages_payload.append({"role": "user", "content": full_content})
                else:
                    # Standard GPT-4o Logic
                    messages_payload.append({"role": "system", "content": system_prompt})
                    
                    # Add history messages
                    for msg in history:
                        messages_payload.append(msg)
                        
                    # Add current message
                    messages_payload.append({"role": "user", "content": current_interaction_text})

                # 4. Call API
                api_args = {
                    "model": model,
                    "messages": messages_payload,
                    token_arg_name: 300 
                }

                response = await self.client.chat.completions.create(**api_args)
                reply_text = response.choices[0].message.content
                
                # 5. Send Reply
                await message.reply(reply_text, mention_author=True)

                # --- SAVE TO MEMORY ---
                # We save the prompt (user) and the reply (assistant)
                new_history_entries = [
                    {"role": "user", "content": current_interaction_text},
                    {"role": "assistant", "content": reply_text}
                ]
                
                # Add to existing history
                history.extend(new_history_entries)
                
                # TRIM HISTORY (Keep only last 6 interactions to save money/tokens)
                if len(history) > 6: 
                    history = history[-6:]
                
                await self.config.channel(message.channel).history.set(history)
                # ----------------------

            except Exception as e:
                await message.reply(f"❌ **Error:** {str(e)}", mention_author=True)
                print(f"Error in Condescend cog: {e}")
