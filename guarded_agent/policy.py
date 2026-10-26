"""Deterministic, in-memory policy state; integer amounts use smallest asset units."""
from dataclasses import dataclass, field
from threading import Lock
from .keys import ScopedKey

@dataclass(frozen=True)
class Verdict:
    decision: str
    reason: str

@dataclass
class Policy:
    spending_cap: int
    max_single_amount: int
    recipients: frozenset
    allowed_methods: frozenset
    velocity_limit: int
    window_seconds: int = 60
    _history: list = field(default_factory=list, init=False, repr=False)
    _lock: object = field(default_factory=Lock, init=False, repr=False)
    _last_now: object = field(default=None, init=False, repr=False)

    def __post_init__(self):
        for value in (self.spending_cap, self.max_single_amount, self.velocity_limit, self.window_seconds):
            if type(value) is not int or value <= 0:
                raise ValueError('policy limits must be positive integers')

    def evaluate(self, intent, key: ScopedKey, contract, method, now, gas_budget=0):
        with self._lock:
            reason = self._check(intent, key, contract, method, now, gas_budget)
            if reason:
                return Verdict('BLOCK', reason)
            self._history.append((now, int(intent['amount']), gas_budget))
            return Verdict('ALLOW', 'policy_satisfied')

    def _check(self, intent, key, contract, method, now, gas_budget):
        if type(now) is not int or (self._last_now is not None and now < self._last_now):
            return 'invalid_time'
        self._last_now = now
        try:
            raw = intent['amount']
            if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or int(raw) <= 0:
                return 'invalid_intent'
            amount = int(raw)
            if any(not isinstance(intent[k], str) or not intent[k] for k in ('asset_in', 'asset_out', 'receiver')):
                return 'invalid_intent'
            if type(intent['deadline']) is not int:
                return 'invalid_intent'
        except (KeyError, TypeError, ValueError):
            return 'invalid_intent'
        if type(gas_budget) is not int or gas_budget < 0:
            return 'invalid_gas_budget'
        if intent['deadline'] <= now:
            return 'intent_expired'
        if intent['receiver'] not in self.recipients:
            return 'recipient_not_allowed'
        if method not in self.allowed_methods:
            return 'method_not_allowed'
        reason = key.check(contract, method, gas_budget)
        if reason:
            return reason
        # Allowance models cumulative gas budget, not transferred token value.
        if key.allowance is not None and sum(h[2] for h in self._history) + gas_budget > key.allowance:
            return 'key_allowance_exceeded'
        if amount > self.max_single_amount:
            return 'single_amount_exceeded'
        active = [h for h in self._history if h[0] > now - self.window_seconds]
        if sum(h[1] for h in active) + amount > self.spending_cap:
            return 'spending_cap_exceeded'
        if len(active) >= self.velocity_limit:
            return 'velocity_exceeded'
        return None
