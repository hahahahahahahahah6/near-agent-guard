"""Append-only API with hash chaining; retain an external head to detect truncation."""
import hashlib
import json
from pathlib import Path
from .intent import canonical_json

GENESIS = '0' * 64

def row_hash(row):
    return hashlib.sha256(canonical_json(row).encode()).hexdigest()

class AuditLog:
    def __init__(self, path):
        self.path = Path(path)

    def verify(self, expected_head=None):
        head = GENESIS
        try:
            if self.path.exists():
                with self.path.open(encoding='utf-8') as stream:
                    for line in stream:
                        row = json.loads(line)
                        stored = row.pop('hash')
                        if row['previous_hash'] != head or row_hash(row) != stored:
                            return False
                        head = stored
            return expected_head is None or head == expected_head
        except (ValueError, KeyError, TypeError, OSError):
            return False

    def append(self, event):
        if not self.verify():
            raise ValueError('audit chain is invalid')
        head = GENESIS
        if self.path.exists():
            with self.path.open(encoding='utf-8') as stream:
                for line in stream:
                    head = json.loads(line)['hash']
        row = dict(event=event, previous_hash=head)
        row['hash'] = row_hash(row)
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(canonical_json(row) + '\n')
        return row
