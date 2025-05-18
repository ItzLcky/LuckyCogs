import discord
from redbot.core import commands
import random

class Fortune(commands.Cog):
    """Randomly generated fortunes."""

    def __init__(self, bot):
        self.bot = bot

        self.beginnings = [
            "A black cat", "A lost thought", "A sudden breeze", "The whispering wind", "Your reflection",
            "A midnight visitor", "The ringing bell", "A crimson moon", "A cold drink", "A quiet night",
            "An old melody", "A broken mirror", "A locked drawer", "The flickering light", "A ticking watch",
            "A spilled secret", "An unopened letter", "A forgotten road", "The silent stars", "A misty alley",
            "An open door", "A creeping shadow", "A restless dream", "A missed call", "A wandering soul",
            "A burnt match", "The smell of rain", "A cracked photo", "The falling leaves", "A closed book",
            "An unseen figure", "A laughing ghost", "A foggy window", "An unfinished sentence", "The distant howl",
            "A flicked switch", "The rustling leaves", "The scent of lavender", "The fading sun", "A hollow laugh",
            "A dusty attic", "An empty street", "A ticking metronome", "A dim hallway", "A whispered name",
            "A sudden chill", "The shifting shadows", "An empty cup", "A stained letter", "A paused song",
            "The color red", "A hesitant glance", "The hum of silence", "An awkward pause", "A cracked screen",
            "A melting candle", "A ruffled curtain", "The morning fog", "The final word", "A polished stone"
        ]

        self.verbs = [
            "will lead you astray", "offers clarity", "foretells madness", "brings laughter",
            "marks a choice", "tests your faith", "invites danger", "warns of betrayal",
            "sings your fate", "speaks of fortune", "pulls the strings", "masks a lie",
            "lights the path", "dares you onward", "awakens your courage", "feeds a fire",
            "echoes your fear", "opens a door", "sows confusion", "rests in your hands",
            "hides a truth", "calls your name", "steals your peace", "remembers your past",
            "nudges your fate", "shines with hope", "breathes with life", "reveals intentions",
            "guards a secret", "bends reality", "tests your resolve", "clouds your vision",
            "asks for trust", "hides in plain sight", "breaks the silence", "mirrors your heart",
            "awaits your answer", "grants a gift", "fades with time", "grows stronger",
            "follows your steps", "blurs the line", "demands patience", "pulls the thread",
            "casts a shadow", "seeks redemption", "brings closure", "mocks your doubt",
            "offers peace", "drains your energy"
        ]

        self.endings = [
            "before the sun sets.", "as the candle fades.", "under the old oak tree.",
            "when silence falls.", "on the edge of reason.", "before the last leaf drops.",
            "at the break of dawn.", "inside your quiet moment.", "when the winds shift.",
            "after the third knock.", "when the stars fall.", "before the glass shatters.",
            "on the eve of chaos.", "in the still of night.", "when the truth is spoken.",
            "beneath the blood moon.", "after the rain stops.", "when shadows lengthen.",
            "on your next breath.", "at the closing of the gate.", "beneath the cold sky.",
            "during a passing storm.", "as your memory fades.", "when the sky turns red.",
            "in the hush of midnight.", "on the seventh hour.", "beneath the city lights.",
            "after the final toast.", "in a room of mirrors.", "at the turn of the page.",
            "on your final step.", "beneath a stranger’s smile.", "after the song ends.",
            "before the words are said.", "in the echo of laughter.", "on the old staircase.",
            "as the winds hush.", "before the mask slips.", "beneath the forgotten stone.",
            "in the warmth of silence.", "at the crossroads of fate.", "in a dream half-remembered.",
            "at the sound of bells.", "as footsteps vanish.", "before the ink dries.",
            "at the fall of a coin.", "underneath the bed.", "while no one is looking.",
            "when dusk turns to night.", "as you turn around."
        ]

    @commands.command(name="fortune")
    async def fortune(self, ctx):
        """Receive a randomly generated fortune."""
        part1 = random.choice(self.beginnings)
        part2 = random.choice(self.verbs)
        part3 = random.choice(self.endings)

        fortune = f"{part1} {part2} {part3}"
        await ctx.send(f"🔮 {fortune}")
