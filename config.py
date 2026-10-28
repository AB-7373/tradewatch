import os

BASE_URL = os.getenv("TYPESAFE_BASE_URL", "https://api.codiv.ai")
API_KEY = os.getenv("TYPESAFE_API_KEY", "")
MODEL = os.getenv("JEV_MODEL", "openjev-latest")

TICKER = "^NSEI"      # NIFTY 50 on Yahoo Finance
HORIZON = 3           # predict this many hourly bars ahead
FLAT_BAND = 0.001     # moves smaller than +/-0.1% count as "flat"
CLASSES = ("up", "down", "flat")

CACHE_FILE = "jev_cache.json"
STATE_FILE = "state.json"
