"""Local model of NEAR access-key permissions, not an installed chain key."""
from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass(frozen=True)
class ScopedKey:
    receiver_id: str
    method_names: Tuple[str, ...]
    allowance: Optional[int]
    full_access: bool = False

    def check(self, receiver_id, method, gas_budget):
        if self.full_access:
            return 'full_access_key_refused'
        if receiver_id != self.receiver_id:
            return 'key_receiver_mismatch'
        # NEAR's empty method list permits any method on this receiver.
        if self.method_names and method not in self.method_names:
            return 'key_method_not_allowed'
        if self.allowance is not None and gas_budget > self.allowance:
            return 'key_allowance_exceeded'
        return None
