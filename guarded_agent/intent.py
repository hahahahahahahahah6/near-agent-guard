"""Standards-shaped local intent envelopes; not a NEP-413 wire implementation."""
import hashlib
import json
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def make_intent(asset_in, asset_out, amount, receiver, deadline):
    return dict(asset_in=asset_in, asset_out=asset_out, amount=str(amount), receiver=receiver, deadline=deadline)

def digest(intent):
    return hashlib.sha256(canonical_json(intent).encode('utf-8')).hexdigest()

def sign_intent(intent):
    key = Ed25519PrivateKey.generate()
    hashed = digest(intent)
    return dict(intent=intent, digest=hashed, algorithm='Ed25519',
                public_key=key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex(),
                signature=key.sign(bytes.fromhex(hashed)).hex())

def verify_intent(envelope):
    try:
        hashed = digest(envelope['intent'])
        if envelope['algorithm'] != 'Ed25519' or hashed != envelope['digest']:
            return False
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(envelope['public_key'])).verify(
            bytes.fromhex(envelope['signature']), bytes.fromhex(hashed))
        return True
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False
