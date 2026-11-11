from dataclasses import dataclass
from trades import close_trade


@dataclass
class Cfg:
    entry: float = 0.85     # confidence needed to count as a strong signal
    exit: float = 0.60      # confidence below this means 'get out' (hysteresis)
    persist: int = 3        # strong signal needed this many bars in a row
    cooldown: int = 3       # bars to wait after exiting
    cost: float = 0.0005    # 0.05% per round trip

    def __post_init__(self):
        if not 0 < self.exit < self.entry <= 1:
            raise ValueError(f"Exit line ({self.exit}) must be below the entry line ({self.entry}). "
                             "Otherwise every trade would be closed on the very next bar.")
        if self.persist < 1 or self.cooldown < 0:
            raise ValueError("persist must be at least 1 and cooldown cannot be negative.")
        if not 0 <= self.cost < 0.05:
            raise ValueError("cost is a fraction per round trip, e.g. 0.0005 = 0.05%.")


class Machine:
    """Watches ONE probability stream (P(up) for longs, P(down) for shorts).

    It only DECIDES. Filling the order at a price is the Runner's job.
    """

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
    """Used by BOTH backtest and live poll, so they can never drift apart.

    Timing (no lookahead): the decision for bar t uses bar t's close, which is
    only known once bar t has finished. So the order is filled at the OPEN of
    bar t+1. Between the two, the order is 'pending'. Pending orders are saved
    in to_dict(), so a live poll that ends right after a signal fills it on the
    next poll, exactly like the backtest would.
    """
    SIDES = ("long", "short")

    def __init__(self, cfg, state=None):
        self.cfg = cfg
        self.m = {s: Machine(cfg) for s in self.SIDES}
        self.open = {s: None for s in self.SIDES}
        self.pending = {s: None for s in self.SIDES}     # "ENTER" / "EXIT" / None
        self.closed, self.last_ts, self.last_close = [], None, None
        if state:
            for s in self.SIDES:
                for k, v in state["machines"][s].items():
                    setattr(self.m[s], k, v)
            self.open, self.closed, self.last_ts = state["open"], state["closed"], state["last_ts"]
            self.pending = state.get("pending") or {s: None for s in self.SIDES}
            self.last_close = state.get("last_close")

    def process(self, ts, open_price, close_price, p_up, p_down):
        # 1) Fill orders decided on the previous bar, at this bar's open.
        for side in self.SIDES:
            order, self.pending[side] = self.pending[side], None
            if order == "ENTER":
                self.open[side] = {"side": side, "signal_time": self.last_ts,
                                   "entry_time": str(ts), "entry_price": float(open_price)}
            elif order == "EXIT" and self.open[side]:
                self.closed.append(close_trade(self.open[side], ts, open_price,
                                               self.cfg.cost, "CLOSED"))
                self.open[side] = None
        # 2) Decide, using this bar's (now finished) data. Fills happen next bar.
        for side, p in (("long", p_up), ("short", p_down)):
            ev = self.m[side].step(p)
            if ev:
                self.pending[side] = ev
        self.last_ts, self.last_close = str(ts), float(close_price)

    def all_trades(self, last_price=None, last_ts=None):
        """Closed trades plus any still-open ones marked at the latest close.
        An entry signalled on the very last bar has no next bar to fill on, so it is
        not a trade yet (see self.pending)."""
        last_price = self.last_close if last_price is None else last_price
        last_ts = self.last_ts if last_ts is None else last_ts
        t = list(self.closed)
        for o in self.open.values():
            if o:
                t.append(close_trade(o, last_ts, last_price, self.cfg.cost, "OPEN"))
        return t

    def to_dict(self):
        return {"machines": {s: self.m[s].to_dict() for s in self.SIDES},
                "open": self.open, "pending": self.pending, "closed": self.closed,
                "last_ts": self.last_ts, "last_close": self.last_close}
