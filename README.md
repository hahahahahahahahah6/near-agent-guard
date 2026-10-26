# near-agent-guard

A deterministic policy guard for AI agents proposing money moves on NEAR.
Proposals pass recipient, method, spending, velocity, expiry, and key-scope checks
before the CLI or demo creates a local signature. Every displayed decision has a
hash-chained audit entry. This is an offline prototype for the **AI Security &
Defense** track, licensed under MIT.

## Run it and see the result

Run these commands from this project's root. The runtime requires Python 3.9+
and an existing `cryptography` installation. Nothing needs a NEAR account or funds.
All commands use `python3`; no network installation is needed or attempted.

1. Check the crypto dependency:

   ```sh
   python3 -c 'import cryptography; print(cryptography.__version__)'
   ```

   See the installed version (this build used 50.0.1). Signing uses real
   Ed25519 from this package; there is no HMAC substitute or fake signature.

2. Run the offline demo:

   ```sh
   python3 demo.py
   # Equivalent entry point:
   python3 -m guarded_agent.demo
   ```

   See six named scenarios: `allowed: ALLOW policy_satisfied`, followed by
   `over-cap: BLOCK spending_cap_exceeded`, `recipient: BLOCK recipient_not_allowed`,
   `key-method: BLOCK key_method_not_allowed`,
   `velocity (third payment): BLOCK velocity_exceeded`, and
   `expired: BLOCK intent_expired`. Each has an `audit:` JSON line. The allowed
   case also prints a signed intent which the demo verifies. Finally see
   `audit_verified: True`. The cap and velocity scenarios start with isolated,
   seeded policy histories. Demo timestamps and verdicts are deterministic;
   ephemeral public keys and signatures vary on every run.

   `demo-audit.jsonl` accumulates entries without overwriting earlier runs.
   Use `--audit another-demo.jsonl` to select another log.

3. Run tests:

   ```sh
   python3 -m pytest -q
   ```

   If pytest is already installed, see the passing test count. If unavailable
   (as on the build machine), run the same unittest-compatible tests using:

   ```sh
   python3 -m unittest discover -v
   ```

   See `Ran 27 tests` and `OK`. Tests cover every policy block reason,
   receiver/method/allowance scope, full-access refusal, window rollover,
   signature verification and tampering, audit tampering and pinned-head
   truncation detection, CLI signing order, and mocked RPC success/offline paths.
   Tests require no network.

4. Propose an allowed local transfer:

   ```sh
   python3 -m guarded_agent.cli propose --help
   python3 -m guarded_agent.cli propose --receiver alice.testnet --amount 10
   ```

   See usage, then a JSON verdict containing `ALLOW` and its audit row, followed
   by a signed intent JSON envelope. Amounts are integer smallest units, not
   NEAR decimal values. To see a blocked proposal with no signed envelope:

   ```sh
   python3 -m guarded_agent.cli propose --receiver mallory.testnet --amount 10
   ```

   See `BLOCK` / `recipient_not_allowed`; the process exits with status 2.
   Allowed proposals exit with status 0. `--deadline` accepts Unix seconds;
   its default is current time plus 60 seconds. `--audit` selects the log path.

5. Optionally read public testnet data:

   ```sh
   python3 -m guarded_agent.cli propose --receiver alice.testnet --amount 10 --rpc --account alice.testnet
   ```

   See an additional JSON object with node status and account state, or a
   structured error if the network/account is unavailable. Network transport
   errors include `offline: true`; they do not interrupt the offline guard.
   This step is optional and was tested with mocks, not a live RPC call.

## Exact NEAR technology used

- **Function-call access-key permission model:** `ScopedKey` models
  `receiver_id`, `method_names`, and `allowance`, and refuses full-access agent
  keys. The receiver is the contract account, separate from the intent's payment
  recipient. An empty method list allows every method on that receiver, matching
  NEAR's permission semantics. `None` means unlimited allowance; zero allows no
  positive gas budget. The model checks proposed gas budgets against cumulative
  allowance for the lifetime of the Policy instance. It does not charge payment
  principal against gas allowance. No chain access key is created or installed.
  Actual function-call keys cannot attach native NEAR deposits; the illustrated
  `ft_transfer` is a policy example, not an executable chain transaction.
- **NEAR Intents-inspired, standards-shaped intent construction:** a dictionary
  contains `asset_in`, `asset_out`, string integer `amount`, payment `receiver`,
  and Unix-second `deadline`. Sorted-key compact UTF-8 JSON (`ensure_ascii=False`,
  no NaN) is hashed with SHA-256. An ephemeral Ed25519 key signs the 32 digest
  bytes; the envelope includes its public key, digest and signature, and can be
  verified locally. This is our local envelope format, not a claim of compliance
  with a deployed NEAR Intents verifier or NEP-413 signing format.
- **NEAR testnet JSON-RPC:** optional `urllib` HTTPS requests to
  `https://rpc.testnet.near.org` call only `status` and `query` with
  `request_type: view_account` and `finality: final`. Each request has a five
  second timeout. No quote endpoint or transaction method is called.

## Policy and audit behavior

The CLI uses a fixed sample policy: cap 100 per rolling 60 seconds, maximum
single amount 60, recipient `alice.testnet`, method `ft_transfer`, and at most
two allowed proposals per window. The scoped receiver is `token.testnet`, with
an illustrative gas allowance of 1000 and gas budget 1 per CLI proposal. Demo
policies allow `withdraw` at the policy layer to demonstrate that the narrower
key independently blocks it. Demo maximum single amount is 80.

`Policy.evaluate` accepts explicit integer time for reproducibility and refuses
backward time. It checks malformed input, expiry, recipient, policy method, key
scope, single amount, rolling cap and velocity, in that order. Expiry at exactly
`deadline` is blocked. A window covers `(now - window_seconds, now]`. Allowed
proposals reserve spend/count/gas immediately; blocked proposals consume none.
One instance serializes evaluations with a lock.

State is in memory and resets with a new Policy or CLI invocation. The CLI is
therefore a one-proposal demonstration, not persistent wallet protection. The
cap assumes a single asset denomination; no exchange valuation or multi-asset
risk accounting is implemented. Use a separate policy per denomination. A
production integration would also need trusted state, persistent atomic
reservations, authenticated policy configuration, replay protection, and a
signer that binds and rechecks the exact execution context. This local intent
does not sign contract/method/gas parameters. The standalone signing utility
is not a security boundary; the demo and CLI are the guarded entry points.

`AuditLog.append` first verifies the existing chain, then appends one JSON line
containing the event, previous hash and SHA-256 hash of the canonical row without
its `hash` field. `verify(expected_head=...)` can pin a separately retained head
hash to detect truncation. Without a trusted external head, a local attacker can
rewrite the entire chain or remove its tail undetected. The API is append-only,
not immutable storage, and assumes a single writer; there is no multi-process
lock, crash-atomic transaction, or durable filesystem sync guarantee. Logs hold
proposal data, never private signing keys. Ephemeral private keys are not saved.

## What this is NOT

This project does **not** provide TEE attestation, Chain Signatures MPC signing,
1-Click Swap execution, mainnet or testnet broadcast, or movement of real funds.
It requests no 1-Click swap quote. Locally signed intents are not submitted to
any settlement service. Ephemeral signatures prove envelope integrity, not the
identity or chain authorization of a funded wallet. No accounts are created and
no hackathon submission is made. This is a prototype for review, with build and
polish planned for the November 1–14, 2026 build window.

## Files

`guarded_agent/policy.py` handles decisions; `keys.py` scope; `intent.py` hashing
and Ed25519; `audit.py` hash chains; `near_rpc.py` read-only queries; `cli.py` the
proposal interface; `demo.py` the six scenarios. `tests/test_guard.py` runs under
both pytest and unittest. Contributions and reuse are welcome under the MIT
license; see `LICENSE` (Copyright 2026 hao li).
