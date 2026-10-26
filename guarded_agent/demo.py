"""Six reproducible, offline scenarios; audit hashes repeat for identical runs."""
import argparse
from dataclasses import asdict
import json
from .audit import AuditLog
from .intent import make_intent, sign_intent, verify_intent
from .keys import ScopedKey
from .policy import Policy

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', default='demo-audit.jsonl')
    args = parser.parse_args(argv)
    audit = AuditLog(args.audit)
    now = 1800000000
    key = ScopedKey('token.testnet', ('ft_transfer',), 1000)

    def fresh():
        return Policy(100, 80, frozenset({'alice.testnet'}), frozenset({'ft_transfer', 'withdraw'}), 2)

    def intent(amount=10, receiver='alice.testnet', deadline=now + 60):
        return make_intent('demo:token', 'demo:token', amount, receiver, deadline)

    capped = fresh()
    capped.evaluate(intent(70), key, 'token.testnet', 'ft_transfer', now)
    fast = fresh()
    for _ in range(2):
        fast.evaluate(intent(), key, 'token.testnet', 'ft_transfer', now)
    scenarios = [
        ('allowed', fresh(), intent(), 'ft_transfer'),
        ('over-cap', capped, intent(40), 'ft_transfer'),
        ('recipient', fresh(), intent(receiver='mallory.testnet'), 'ft_transfer'),
        ('key-method', fresh(), intent(), 'withdraw'),
        ('velocity (third payment)', fast, intent(), 'ft_transfer'),
        ('expired', fresh(), intent(deadline=now), 'ft_transfer'),
    ]
    for name, policy, proposal, method in scenarios:
        verdict = policy.evaluate(proposal, key, 'token.testnet', method, now)
        row = audit.append(dict(scenario=name, verdict=asdict(verdict), intent=proposal,
                                contract='token.testnet', method=method, gas_budget=0, timestamp=now))
        print('{}: {} {}'.format(name, verdict.decision, verdict.reason))
        print('audit: ' + json.dumps(row, sort_keys=True))
        if verdict.decision == 'ALLOW':
            signed = sign_intent(proposal)
            assert verify_intent(signed)
            print('signed_intent: ' + json.dumps(signed, sort_keys=True))
    print('audit_verified: ' + str(audit.verify()))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
