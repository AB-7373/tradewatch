from dataclasses import dataclass
from trades import close_trade


@dataclass
class Cfg:
    entry: float = 0.85     # confidence needed to count as a strong signal
    exit: float = 0.60      # confidence below this means 'get out' (hysteresis)
    persist: int = 3        # strong signal needed this many bars in a row
    cooldown: int = 3       # bars to wait after exiting
    cost: float = 0.0005    # 0.05% per round trip


class Machine:
    """Watches ONE probability stream (P(up) for longs, P(down) for shorts)."""

    def __init__(self, cfg):
        self.cfg, self.in_pos, self.streak, self.cool = cfg, False, 0, 0

    def step(self, p):
        c = self.cfg
        if self.in_pos:
            if p < c.exit:
                self.in_pos, self.cool, self.streak = False, c.cooldown, 0
                return "EXIT"
            return None
        if self.cool > 0:
            self.cool -= 1
            self.streak = 0
            return None
        self.streak = self.streak + 1 if p >= c.entry else 0
        if self.streak >= c.persist:
            self.in_pos = True
            return "ENTER"
        return None

    def to_dict(self):
        return {"in_pos": self.in_pos, "streak": self.streak, "cool": self.cool}


class Runner:
    """Used by BOTH backtest and live poll, so they can never drift apart."""
    SIDES = ("long", "short")

    def __init__(self, cfg, state=None):
        self.cfg = cfg
        self.m = {s: Machine(cfg) for s in self.SIDES}
        self.open = {s: None for s in self.SIDES}
        self.closed, self.last_ts = [], None
        if state:
            for s in self.SIDES:
                for k, v in state["machines"][s].items():
                    setattr(self.m[s], k, v)
            self.open, self.closed, self.last_ts = state["open"], state["closed"], state["last_ts"]

    def process(self, ts, price, p_up, p_down):
        for side, p in (("long", p_up), ("short", p_down)):
            ev = self.m[side].step(p)
            if ev == "ENTER":
                self.open[side] = {"side": side, "entry_time": str(ts), "entry_price": float(price)}
            elif ev == "EXIT" and self.open[side]:
                self.closed.append(close_trade(self.open[side], ts, price, self.cfg.cost, "CLOSED"))
                self.open[side] = None
        self.last_ts = str(ts)

    def all_trades(self, last_price, last_ts):
        """Closed trades plus any still-open ones marked at the latest price."""
        t = list(self.closed)
        for o in self.open.values():
            if o:
                t.append(close_trade(o, last_ts, last_price, self.cfg.cost, "OPEN"))
        return t

    def to_dict(self):
        return {"machines": {s: self.m[s].to_dict() for s in self.SIDES},
                "open": self.open, "closed": self.closed, "last_ts": self.last_ts}
