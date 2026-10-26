"""Propose local intents; no transaction is broadcast."""
import argparse
from dataclasses import asdict
import json
import time
from .audit import AuditLog
from .intent import make_intent, sign_intent
from .keys import ScopedKey
from .policy import Policy
from . import near_rpc

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    propose = subs.add_parser('propose', help='evaluate a local transfer proposal')
    propose.add_argument('--receiver', required=True)
    propose.add_argument('--amount', required=True, type=int)
    propose.add_argument('--deadline', type=int, help='Unix seconds; default now + 60')
    propose.add_argument('--method', default='ft_transfer')
    propose.add_argument('--contract', default='token.testnet')
    propose.add_argument('--audit', default='audit.jsonl')
    propose.add_argument('--rpc', action='store_true', help='also fetch read-only testnet status')
    propose.add_argument('--account', help='optional read-only testnet account query')
    args = parser.parse_args(argv)
    now = int(time.time())
    intent = make_intent('demo:token', 'demo:token', args.amount, args.receiver,
                         args.deadline if args.deadline is not None else now + 60)
    policy = Policy(100, 60, frozenset({'alice.testnet'}), frozenset({'ft_transfer'}), 2)
    key = ScopedKey('token.testnet', ('ft_transfer',), 1000)
    verdict = policy.evaluate(intent, key, args.contract, args.method, now, gas_budget=1)
    row = AuditLog(args.audit).append(dict(verdict=asdict(verdict), intent=intent, contract=args.contract, method=args.method, gas_budget=1, timestamp=now))
    print(json.dumps(dict(verdict=asdict(verdict), audit=row), sort_keys=True))
    if verdict.decision == 'ALLOW':
        print(json.dumps(sign_intent(intent), sort_keys=True))
    if args.rpc or args.account:
        result = dict(status=near_rpc.status())
        if args.account:
            result['account'] = near_rpc.account(args.account)
        print(json.dumps(dict(rpc=result), sort_keys=True))
    return 0 if verdict.decision == 'ALLOW' else 2

if __name__ == '__main__':
    raise SystemExit(main())
