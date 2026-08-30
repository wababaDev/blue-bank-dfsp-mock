# Blue Bank Mock DFSP

A small, self-contained mock of a DFSP's core banking API — built to develop and test the `bluebank-zm-dfsp-cc` Core Connector against something with real, persistent state, a real ledger, and a real distinction between a cancelled hold and a genuine refund.

## Why this exists

A stateless mock (like the ML Testing Toolkit's `cbs-mock`) returns the same response every time, with nothing behind it. This mock uses a real SQLite file, so reserving, committing, unreserving, debiting, and refunding all genuinely change account balances — and every single change is recorded in an actual general ledger you can inspect afterward.

## Auth

Every route requires:
```
Authorization: Bearer <token>
```
Read from `AUTH_TOKEN` (env var), defaulting to `1000000000`. Missing/wrong token returns `401`.

## Response shape

```json
// success
{ "success": true, "data": { ... } }

// error
{ "success": false, "error": { "code": 404, "message": "Account not found" } }
```

## The two sides — unreserve vs refund

These are deliberately **separate** endpoints, because they mean different things:

- **Unreserve** — cancels a hold that never finished. Nothing was ever really given to anyone, so nothing needs undoing — just release the hold and restore the balance. Only works on a reservation still in `RESERVED` state.
- **Refund** — reverses a debit that already completed for real. Real money already left the account, so this is a genuine second transaction giving it back. Only works on a debit still in `COMPLETED` state.

Trying to unreserve something already `COMMITTED`, or refund something already `REFUNDED`, correctly returns a `422` — these operations are not interchangeable, on purpose.

## Endpoints

### Payee side (money arriving for this DFSP's customer) — reserve is a marker, commit is the only real credit

| Method | Path | Maps to `ICbsClient` method |
|---|---|---|
| `POST` | `/funds/reserve` | `reserveFunds` — creates a pending marker. **Does NOT touch the balance** — the customer never had this money yet, so there's nothing to hold on their side |
| `POST` | `/funds/commit` | `commitReservedFunds` — the **only** point the balance actually changes. Finalizes a `RESERVED` marker into a real credit |
| `POST` | `/funds/unreserve` | `unreserveFunds` — cancels a `RESERVED` marker. No balance change needed, since reserve never touched it |

### Payer side (this DFSP's customer sending money out) — called directly by the app, not the connector

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/debits` | Called by **the app**, directly against the CBS — immediate, real debit, before the connector is even told to proceed. Keyed on `home_transaction_id`, the app's own reference. |
| `POST` | `/debits/refund` | `handleRefund` — called by **the connector**, later, if something fails. Looked up by `home_transaction_id` — the connector never sees the CBS's internal `debit_id` at all. |

This matches the actual sequence: the app debits the customer *before* calling the connector (`PUT /send-money/{id} {acceptQuote: true, homeTransactionId}`), so the connector's only path back to that debit, if a refund is ever needed, is the `home_transaction_id` — never a CBS-internal ID it was never given.

### Simulate — stands in for the DFSP's own customer-facing app

These exist so you can exercise the full payer-side flow without writing a separate test harness. Controlled by one env var:

```
MODE=test   # never calls the connector — returns a canned response in the same shape
MODE=live   # really calls the connector at CORE_CONNECTOR_URL
```

| Method | Path | What it does |
|---|---|---|
| `POST` | `/simulate/send-money` | Asks for a quote. `live` really `POST`s to `{CORE_CONNECTOR_URL}/send-money`; `test` returns a canned quote — never touches money either way. |
| `POST` | `/simulate/accept-quote` | **Always really debits** the CBS first — that's genuine bank behavior regardless of mode. `live` then really `PUT`s `{CORE_CONNECTOR_URL}/send-money/{transactionId}`; `test` returns a canned accept response instead. |

Refunding is never triggered from these endpoints — if a `live` transfer fails after `/simulate/accept-quote`, it's the **connector's** job to call `/debits/refund` itself, using the `home_transaction_id` it was already given.

### Lookups / visibility

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/accounts/{account_id}` | `getAccountInfo` |
| `GET` | `/accounts/{account_id}/balance` | Current balance — for smoke tests |
| `GET` | `/accounts/{account_id}/ledger` | Every GL entry for this account, in order — the actual paper trail behind the balance |
| `POST` | `/quotes` | `getQuote` |

## Seed accounts

| Account ID | Name | Currency | Balance | Status |
|---|---|---|---|---|
| `260970000000` | Mercy Uzumaki | ZMW | 5000.0 | active |
| `260970000001` | Faith Nara | ZMW | 1200.0 | active |
| `260970000002` | Selina Uchiha | ZMW | 0.0 | active |
| `260970000003` | Peace Yagami | ZMW | 10000.0 | active |
| `260970000004` | John Aizen | ZMW | 0.0 | blocked |

## Running locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 4040
```

## Running with Docker

```bash
docker build -t bluebank-mock .
docker run -p 4040:4040 \
  -e AUTH_TOKEN=1000000000 \
  -e MODE=test \
  -e CORE_CONNECTOR_URL=http://host.docker.internal:3004 \
  bluebank-mock
```

`MODE` and `CORE_CONNECTOR_URL` only matter for the `/simulate/*` endpoints — everything else in this mock behaves the same regardless.

## Testing the full flow

`rest.http` walks through, in order: account lookup, auth failures, reserve → commit, reserve → unreserve (with the wrong-state 422 cases deliberately included), debit → refund, and a final ledger check showing every one of those movements in sequence.

## Not implemented (on purpose, for now)

- Multiple currencies per account.
- Any notion of a due-diligence/compliance check.
- Token expiry.

Everything here is deliberately minimal — the goal was a fast, honest target to build the real connector against, not a full bank simulator.