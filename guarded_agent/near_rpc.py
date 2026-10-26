"""Optional read-only NEAR testnet RPC, with bounded network wait."""
import json
import urllib.request

ENDPOINT = 'https://rpc.testnet.near.org'

def _call(method, params):
    request = urllib.request.Request(ENDPOINT, data=json.dumps(dict(jsonrpc='2.0', id='guard', method=method, params=params)).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
        if 'result' not in payload:
            return dict(ok=False, error=str(payload.get('error', 'missing result')))
        return dict(ok=True, result=payload['result'])
    except (OSError, ValueError) as exc:
        return dict(ok=False, error=str(exc), offline=True)

def status():
    return _call('status', [])

def account(account_id):
    return _call('query', dict(request_type='view_account', finality='final', account_id=account_id))
