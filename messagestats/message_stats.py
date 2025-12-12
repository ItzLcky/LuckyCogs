import discord
from discord.ext import commands
from collections import defaultdict, Counter
import json
import os
import re


class MessageStats(commands.Cog):
    """A cog to track message counts and most common words per user."""
    
    def __init__(self, bot):
        self.bot = bot
        self.data_file = 'message_stats.json'
        
        # Common conjunctions and other words to exclude
        self.excluded_words = {
            # Conjunctions
            'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
            # Common articles
            'a', 'an', 'the',
            # Common prepositions
            'in', 'on', 'at', 'to', 'from', 'by', 'with', 'of', 'about',
            'for', 'as', 'into', 'onto', 'upon', 'over', 'under', 'above',
            'below', 'through', 'between', 'among', 'during', 'before',
            'after', 'since', 'until', 'within', 'without', 'toward',
            # Common pronouns
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him',
            'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our',
            'their', 'mine', 'yours', 'hers', 'ours', 'theirs', 'this',
            'that', 'these', 'those', 'who', 'what', 'which', 'whom',
            'whose',
            # Common verbs
            'is', 'am', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did',
            # Other common words
            'not', 'no', 'yes', 'can', 'could', 'will', 'would', 'should',
            'may', 'might', 'must', 'shall',
        }
        
        # Load existing data
        self.stats = self.load_stats()
    
    def load_stats(self):
        """Load statistics from JSON file."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def save_stats(self):
        """Save statistics to JSON file."""
        with open(self.data_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
    
    def get_server_stats(self, guild_id):
        """Get or create stats for a specific server."""
        guild_id = str(guild_id)
        if guild_id not in self.stats:
            self.stats[guild_id] = {}
        return self.stats[guild_id]
    
    def get_user_stats(self, guild_id, user_id):
        """Get or create stats for a specific user in a server."""
        server_stats = self.get_server_stats(guild_id)
        user_id = str(user_id)
        if user_id not in server_stats:
            server_stats[user_id] = {
                'message_count': 0,
                'words': {}
            }
        return server_stats[user_id]
    
    def extract_words(self, message_content):
        """Extract words from message, excluding conjunctions and common words."""
        # Convert to lowercase and extract words (alphanumeric only)
        words = re.findall(r'\b[a-z]+\b', message_content.lower())
        
        # Filter out excluded words and very short words
        filtered_words = [
            word for word in words 
            if word not in self.excluded_words and len(word) > 2
        ]
        
        return filtered_words
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages sent by users."""
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return
        
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Get user stats
        user_stats = self.get_user_stats(guild_id, user_id)
        
        # Increment message count
        user_stats['message_count'] += 1
        
        # Extract and count words
        words = self.extract_words(message.content)
        for word in words:
            if word in user_stats['words']:
                user_stats['words'][word] += 1
            else:
                user_stats['words'][word] = 1
        
        # Save stats periodically (every message in this case)
        # For better performance, you could save less frequently
        self.save_stats()
    
    @commands.command(name='mystats')
    async def my_stats(self, ctx):
        """Show your message statistics."""
        user_stats = self.get_user_stats(ctx.guild.id, ctx.author.id)
        
        message_count = user_stats['message_count']
        
        if message_count == 0:
            await ctx.send("You haven't sent any messages yet (or I just started tracking)!")
            return
        
        # Find most common word
        if user_stats['words']:
            most_common_word, word_count = max(
                user_stats['words'].items(), 
                key=lambda x: x[1]
            )
        else:
            most_common_word = "N/A"
            word_count = 0
        
        embed = discord.Embed(
            title=f"📊 Stats for {ctx.author.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Total Messages", 
            value=f"{message_count:,}", 
            inline=False
        )
        embed.add_field(
            name="Most Common Word", 
            value=f"'{most_common_word}' ({word_count} times)", 
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='userstats')
    @commands.has_permissions(manage_messages=True)
    async def user_stats(self, ctx, member: discord.Member):
        """Show message statistics for a specific user."""
        user_stats = self.get_user_stats(ctx.guild.id, member.id)
        
        message_count = user_stats['message_count']
        
        if message_count == 0:
            await ctx.send(f"{member.display_name} hasn't sent any messages yet (or I just started tracking)!")
            return
        
        # Find most common word
        if user_stats['words']:
            most_common_word, word_count = max(
                user_stats['words'].items(), 
                key=lambda x: x[1]
            )
        else:
            most_common_word = "N/A"
            word_count = 0
        
        embed = discord.Embed(
            title=f"📊 Stats for {member.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Total Messages", 
            value=f"{message_count:,}", 
            inline=False
        )
        embed.add_field(
            name="Most Common Word", 
            value=f"'{most_common_word}' ({word_count} times)", 
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='topchatters')
    async def top_chatters(self, ctx, limit: int = 10):
        """Show the top chatters in the server."""
        server_stats = self.get_server_stats(ctx.guild.id)
        
        if not server_stats:
            await ctx.send("No message data available yet!")
            return
        
        # Sort users by message count
        sorted_users = sorted(
            server_stats.items(),
            key=lambda x: x[1]['message_count'],
            reverse=True
        )[:limit]
        
        embed = discord.Embed(
            title=f"🏆 Top {limit} Chatters in {ctx.guild.name}",
            color=discord.Color.gold()
        )
        
        for i, (user_id, stats) in enumerate(sorted_users, 1):
            member = ctx.guild.get_member(int(user_id))
            name = member.display_name if member else f"User {user_id}"
            
            # Get most common word
            if stats['words']:
                most_common_word, word_count = max(
                    stats['words'].items(),
                    key=lambda x: x[1]
                )
                word_info = f"Most used: '{most_common_word}' ({word_count}x)"
            else:
                word_info = "No words tracked"
            
            embed.add_field(
                name=f"{i}. {name}",
                value=f"{stats['message_count']:,} messages\n{word_info}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='topwords')
    async def top_words(self, ctx, member: discord.Member = None, limit: int = 10):
        """Show the top words used by a user (or yourself)."""
        if member is None:
            member = ctx.author
        
        user_stats = self.get_user_stats(ctx.guild.id, member.id)
        
        if not user_stats['words']:
            await ctx.send(f"No word data available for {member.display_name}!")
            return
        
        # Get top words
        top_words = Counter(user_stats['words']).most_common(limit)
        
        embed = discord.Embed(
            title=f"📝 Top {limit} Words for {member.display_name}",
            color=discord.Color.green()
        )
        
        words_list = "\n".join([
            f"{i}. **{word}** - {count} times"
            for i, (word, count) in enumerate(top_words, 1)
        ])
        
        embed.description = words_list
        embed.set_footer(text=f"Total messages: {user_stats['message_count']:,}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='resetstats')
    @commands.has_permissions(administrator=True)
    async def reset_stats(self, ctx):
        """Reset all statistics for this server (Admin only)."""
        guild_id = str(ctx.guild.id)
        
        if guild_id in self.stats:
            del self.stats[guild_id]
            self.save_stats()
            await ctx.send("✅ All statistics for this server have been reset!")
        else:
            await ctx.send("No statistics to reset!")


async def setup(bot):
    """Setup function to load the cog."""
    await bot.add_cog(MessageStats(bot))
