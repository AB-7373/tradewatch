import json, os, time
import numpy as np
import requests
import config
from features import describe


class BaselinePredictor:
    """Simple formula guesser. Works with no API key."""
    name = "baseline"

    def predict(self, ts, row):
        z = row.trend / (row.vol_20h * np.sqrt(20) + 1e-9)   # trend measured in 'volatility units'
        logits = np.array([z, -z, 0.0])
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return {"p_up": p[0], "p_down": p[1], "p_flat": p[2]}

    def flush(self):
        pass


class JevPredictor:
    """Talks to Jev / OpenJev. Answers are cached on disk so re-runs cost nothing."""
    name = "jev"

    def __init__(self):
        self.cache = {}
        self.new_calls = 0
        if os.path.exists(config.CACHE_FILE):
            with open(config.CACHE_FILE) as f:
                self.cache = json.load(f)

    def _ask(self, state):
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
        key = f"{config.MODEL}|{ts}|{config.HORIZON}|{config.FLAT_BAND}"
        if key not in self.cache:
            self.cache[key] = self._parse(self._ask(describe(ts, row)))
            self.new_calls += 1
            if self.new_calls % 20 == 0:
                self.flush()
        return self.cache[key]

    def flush(self):
        with open(config.CACHE_FILE, "w") as f:
            json.dump(self.cache, f)
