import hashlib, json, os, time
import numpy as np
import requests
import config
from features import describe

# Read-only snapshot of real OpenJev answers (post-fix prompt) shipped with the
# repo, so the public demo can show Jev's results without an API key.
SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "sample_data", "jev_answers.json")


class BaselinePredictor:
    """Simple formula guesser. Works with no API key.

    It measures the trend in 'volatility units' and leans up if price is above
    its 20-hour average, down if below. It never favours 'flat'.
    """
    name = "baseline"

    def predict(self, ts, row):
        z = row.trend / (row.vol_20h * np.sqrt(20) + 1e-9)
        logits = np.array([z, -z, 0.0])
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return {"p_up": float(p[0]), "p_down": float(p[1]), "p_flat": float(p[2])}

    def missing(self, feats):
        return 0

    def flush(self):
        pass


class JevPredictor:
    """Talks to Jev / OpenJev. Answers are cached on disk so re-runs cost nothing."""
    name = "jev"

    def __init__(self):
        self.cache = {}
        self.new_calls = 0
        for path in (SNAPSHOT_FILE, config.CACHE_FILE):     # local cache wins
            if os.path.exists(path):
                with open(path) as f:
                    self.cache.update(json.load(f))

    @staticmethod
    def key(ts, row):
        # The key includes a fingerprint of the exact text sent, so if the prompt
        # ever changes, old cached answers are not silently reused.
        digest = hashlib.md5(describe(row).encode()).hexdigest()[:12]
        return f"{config.MODEL}|{ts}|{config.HORIZON}|{config.FLAT_BAND}|{digest}"

    def missing(self, feats):
        """How many bars would need a NEW (paid) API call."""
        return sum(self.key(ts, row) not in self.cache for ts, row in feats.iterrows())

    def _ask(self, state):
        if not config.API_KEY:
            raise RuntimeError("No OpenJev API key set (TYPESAFE_API_KEY), and these bars "
                               "are not in the cache.")
        h, b = config.HORIZON, config.FLAT_BAND * 100
        body = {
            "model": config.MODEL,
            "state": state,
            "questions": {"direction": {
                "type": "choice",
                "instructions": f"Over the next {h} hourly bars, will the index close up, down, or flat?",
                "criteria": {
                    "up": f"rises by more than {b:.1f}%",
                    "down": f"falls by more than {b:.1f}%",
                    "flat": f"moves less than {b:.1f}% either way",
                }}},
        }
        headers = {"Authorization": f"Bearer {config.API_KEY}"}
        for attempt in range(4):
            r = requests.post(f"{config.BASE_URL}/v1/systemone", json=body,
                              headers=headers, timeout=60)
            if r.status_code in (429, 529):      # busy or rate-limited: wait and retry
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Model API kept returning busy/rate-limit errors.")

    @staticmethod
    def _parse(resp):
        ans = resp["answers"]["direction"]
        probs = ans["probabilities"]
        if isinstance(probs, list):                # list in the order up, down, flat
            probs = dict(zip(config.CLASSES, probs))
        return {f"p_{c}": float(probs.get(c, 0.0)) for c in config.CLASSES}

    def predict(self, ts, row):
        key = self.key(ts, row)
        if key not in self.cache:
            self.cache[key] = self._parse(self._ask(describe(row)))
            self.new_calls += 1
            if self.new_calls % 20 == 0:
                self.flush()
        return self.cache[key]

    def flush(self):
        if self.new_calls:                         # nothing new -> don't rewrite the file
            with open(config.CACHE_FILE, "w") as f:
                json.dump(self.cache, f)
