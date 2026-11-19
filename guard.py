"""Rate limiting / flood detection / alert throttling. Pure logic with an
injectable clock so it can be tested without sleeping."""
from collections import deque


class Guard:
    def __init__(self, max_updates, window, flood_strikes, flood_window=60):
        self.max_updates = max_updates
        self.window = window
        self.flood_strikes = flood_strikes
        self.flood_window = flood_window
        self._hits = {}
        self._strikes = {}
        self._last = {}  # (kind, key) -> last time something was allowed through

    def check(self, user_id, now):
        """Returns 'ok', 'limited' (drop this update) or 'flood' (ban them)."""
        hits = self._hits.setdefault(user_id, deque())
        hits.append(now)
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) <= self.max_updates:
            return "ok"
        strikes = self._strikes.setdefault(user_id, deque())
        # one strike per window at most, otherwise a single burst would
        # count as many strikes
        if not strikes or now - strikes[-1] > self.window:
            strikes.append(now)
        while strikes and now - strikes[0] > self.flood_window:
            strikes.popleft()
        if len(strikes) >= self.flood_strikes:
            strikes.clear()
            hits.clear()
            return "flood"
        return "limited"

    def cooldown_ok(self, kind, key, now, seconds):
        """True at most once per `seconds` for the same (kind, key)."""
        k = (kind, key)
        last = self._last.get(k)
        if last is not None and now - last < seconds:
            return False
        self._last[k] = now
        return True
