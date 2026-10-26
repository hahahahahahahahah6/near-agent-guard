import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from guarded_agent.audit import AuditLog, GENESIS
from guarded_agent.cli import main
from guarded_agent.intent import make_intent, sign_intent, verify_intent
from guarded_agent.keys import ScopedKey
from guarded_agent.policy import Policy
from guarded_agent import near_rpc

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy(100, 80, frozenset({'alice.testnet'}), frozenset({'ft_transfer', 'withdraw'}), 2)
        self.key = ScopedKey('token.testnet', ('ft_transfer',), 10)
        self.intent = make_intent('demo:a', 'demo:a', 10, 'alice.testnet', 200)

    def check(self, reason, intent=None, key=None, contract='token.testnet', method='ft_transfer', now=100, gas_budget=0):
        verdict = self.policy.evaluate(self.intent if intent is None else intent, self.key if key is None else key, contract, method, now, gas_budget)
        self.assertEqual(verdict.reason, reason)
        self.assertEqual(verdict.decision, 'ALLOW' if reason == 'policy_satisfied' else 'BLOCK')

    def test_allow(self):
        self.check('policy_satisfied')

    def test_single(self):
        self.check('single_amount_exceeded', dict(self.intent, amount='81'))

    def test_cap(self):
        self.check('policy_satisfied', dict(self.intent, amount='70'))
        self.check('spending_cap_exceeded', dict(self.intent, amount='40'))

    def test_recipient(self):
        self.check('recipient_not_allowed', dict(self.intent, receiver='mallory.testnet'))

    def test_policy_method(self):
        self.check('method_not_allowed', method='delete_account')

    def test_key_method(self):
        self.check('key_method_not_allowed', method='withdraw')

    def test_key_receiver(self):
        self.check('key_receiver_mismatch', contract='other.testnet')

    def test_full_access(self):
        self.check('full_access_key_refused', key=ScopedKey('token.testnet', (), None, True))

    def test_allowance(self):
        self.check('key_allowance_exceeded', gas_budget=11)

    def test_cumulative_allowance(self):
        self.check('policy_satisfied', gas_budget=6)
        self.check('key_allowance_exceeded', gas_budget=5)

    def test_unlimited_methods_allowance(self):
        self.check('policy_satisfied', key=ScopedKey('token.testnet', (), None), method='withdraw', gas_budget=999)

    def test_velocity(self):
        self.check('policy_satisfied')
        self.check('policy_satisfied')
        self.check('velocity_exceeded')

    def test_expiry(self):
        self.check('intent_expired', dict(self.intent, deadline=100))

    def test_invalid_intent(self):
        for value in ('0', '-1', '1.5', 'NaN', True, 12):
            with self.subTest(value=value):
                self.check('invalid_intent', dict(self.intent, amount=value))
        self.check('invalid_intent', {})
        self.check('invalid_intent', dict(self.intent, deadline=True))

    def test_invalid_gas(self):
        self.check('invalid_gas_budget', gas_budget=-1)

    def test_invalid_time(self):
        self.check('policy_satisfied')
        self.check('invalid_time', now=99)

    def test_window_boundary(self):
        self.check('policy_satisfied', dict(self.intent, amount='70'))
        self.check('policy_satisfied', dict(self.intent, amount='70'), now=160)

    def test_block_does_not_consume(self):
        self.check('recipient_not_allowed', dict(self.intent, receiver='mallory.testnet'))
        self.check('policy_satisfied')
        self.check('policy_satisfied')

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            Policy(0, 10, frozenset(), frozenset(), 1)

class SigningTests(unittest.TestCase):
    def test_roundtrip(self):
        intent = make_intent('a', 'b', 10, 'alice.testnet', 200)
        signed = sign_intent(intent)
        self.assertTrue(verify_intent(signed))
        signed['intent'] = dict(reversed(list(intent.items())))
        self.assertTrue(verify_intent(signed))

    def test_tampered_signature(self):
        signed = sign_intent(make_intent('a', 'b', 10, 'alice.testnet', 200))
        signed['signature'] = '00' * 64
        self.assertFalse(verify_intent(signed))

    def test_tampered_payload(self):
        signed = sign_intent(make_intent('a', 'b', 10, 'alice.testnet', 200))
        signed['intent']['amount'] = '999'
        self.assertFalse(verify_intent(signed))
        self.assertFalse(verify_intent({}))

class AuditTests(unittest.TestCase):
    def test_chain_and_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.jsonl'
            log = AuditLog(path)
            first = log.append({'decision': 'ALLOW'})
            second = log.append({'decision': 'BLOCK'})
            self.assertEqual(first['previous_hash'], GENESIS)
            self.assertEqual(second['previous_hash'], first['hash'])
            self.assertTrue(log.verify(second['hash']))
            path.write_text(path.read_text().replace('ALLOW', 'BLOCK'))
            self.assertFalse(log.verify())
            with self.assertRaises(ValueError):
                log.append({})

    def test_truncation_with_external_head(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.jsonl'
            log = AuditLog(path)
            log.append({'n': 1})
            head = log.append({'n': 2})['hash']
            path.write_text(path.read_text().splitlines()[0] + '\n')
            self.assertFalse(log.verify(head))

class RPCTests(unittest.TestCase):
    @patch('guarded_agent.near_rpc.urllib.request.urlopen', side_effect=OSError('offline'))
    def test_offline(self, mocked):
        self.assertFalse(near_rpc.status()['ok'])
        self.assertTrue(near_rpc.account('alice.testnet')['offline'])

    @patch('guarded_agent.near_rpc.urllib.request.urlopen')
    def test_queries(self, mocked):
        mocked.return_value.__enter__.return_value = io.StringIO('{"result":{"amount":"12"}}')
        self.assertTrue(near_rpc.account('alice.testnet')['ok'])
        request = mocked.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload['method'], 'query')
        self.assertEqual(payload['params']['request_type'], 'view_account')
        mocked.return_value.__enter__.return_value = io.StringIO('{"error":"unavailable"}')
        self.assertFalse(near_rpc.status()['ok'])

class CLITests(unittest.TestCase):
    def test_cli_allow_block(self):
        with tempfile.TemporaryDirectory() as directory:
            for receiver, expected, lines in [('alice.testnet', 0, 2), ('mallory.testnet', 2, 1)]:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(['propose', '--receiver', receiver, '--amount', '10', '--audit', str(Path(directory) / 'audit.jsonl')])
                self.assertEqual(code, expected)
                rows = output.getvalue().splitlines()
                self.assertEqual(len(rows), lines)
                if code == 0:
                    self.assertTrue(verify_intent(json.loads(rows[1])))

if __name__ == '__main__':
    unittest.main()
