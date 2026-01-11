def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        
        default_global = {
            "api_key": None,
            "model": "gpt-3.5-turbo",
            "system_prompt": "..." # (Keep your existing prompt here)
        }
        self.config.register_global(**default_global)
        
        # NEW: Register channel-specific history
        # We store a list of dictionaries: [{"role": "user", "content": "..."}, ...]
        default_channel = {
            "history": []
        }
        self.config.register_channel(**default_channel)
        
        self.client = None
