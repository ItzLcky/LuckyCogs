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
            # Get the original message object
            replied_msg = message.reference.resolved
            if not replied_msg:
                # If not in cache, fetch it from the API
                channel = self.bot.get_channel(message.channel.id)
                replied_msg = await channel.fetch_message(message.reference.message_id)
            
            # Extract content and NAMES
            original_author = replied_msg.author.display_name
            original_text = replied_msg.content
            
            my_author = message.author.display_name
            # Remove the bot mention from your message so the AI just sees your text
            user_text = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
            
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return # Fail silently if we can't read the context

        # 5. Send to LLM
        async with message.channel.typing():
            try:
                system_prompt = await self.config.system_prompt()
                model = await self.config.model()

                # Fix for o1 models
                is_o1 = model.startswith("o1")
                token_arg_name = "max_completion_tokens" if is_o1 else "max_tokens"
                
                # Construct the conversation context
                # We format it like a script so the LLM understands the flow
                conversation_context = (
                    f"CONTEXT:\n"
                    f"User '{original_author}' said: \"{original_text}\"\n"
                    f"User '{my_author}' (YOU are replying to them) replied: \"{user_text}\"\n\n"
                    f"INSTRUCTION: Reply to '{my_author}' based on their text, but keep the context of what '{original_author}' said in mind."
                )

                messages_payload = []
                if is_o1:
                    # o1: Combine system prompt into user message
                    full_prompt = f"{system_prompt}\n\n{conversation_context}"
                    messages_payload.append({"role": "user", "content": full_prompt})
                else:
                    # GPT-4o / Standard: Use system role
                    messages_payload.append({"role": "system", "content": system_prompt})
                    messages_payload.append({"role": "user", "content": conversation_context})

                api_args = {
                    "model": model,
                    "messages": messages_payload,
                    token_arg_name: 300 
                }

                response = await self.client.chat.completions.create(**api_args)
                
                reply_text = response.choices[0].message.content
                
                # 6. Reply back
                await message.reply(reply_text, mention_author=True)

            except Exception as e:
                await message.reply(f"❌ **Error:** {str(e)}", mention_author=True)
                print(f"Error in Condescend cog: {e}")

            except Exception as e:
                # Send the error to Discord so we can see it
                await message.reply(f"❌ **Error:** {str(e)}", mention_author=True)
                print(f"Error in Condescend cog: {e}")
