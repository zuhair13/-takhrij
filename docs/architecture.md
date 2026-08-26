# Architecture and trust boundaries

## Execution sequence

```mermaid
sequenceDiagram
    participant U as User
    participant A as Public API
    participant P as Pub/Sub
    participant W as Worker
    participant D as ADK workflow
    participant S as SQLite
    participant F as Firestore

    U->>A: POST form, sense, cutoff AH
    A->>F: Transaction: queued + quota
    A->>P: Publish job_id
    A-->>U: 202 + status URL
    P->>W: Signed push
    W->>W: Verify signature, audience, email
    W->>F: Transaction: acquire lease + attempt_id
    W->>D: Run isolated workflow
    D->>S: Exact first-pass lookup
    D->>F: Provisional progress
    D->>D: Devil's Advocate trace audit
    D->>S: Exact follow-up lookup
    D->>D: Issuance Gate
    W->>F: CAS final dossier
    W-->>P: 204 ACK
    U->>A: GET status
    A-->>U: Issued dossier
```

## Trust table

| Value | Authority | Enforcement |
|---|---|---|
| Raw quote | SQLite document | Exact UTF-8 equality at stored code-point span |
| Source ID | SQLite primary key | Gate resolves again before issuance |
| Dates | Manifest columns | Model output is never accepted as date metadata |
| Match existence | Postings lookup | Parameterized SQL equality |
| Match sense | Assessor | Labelled as judgement; confidence and reason retained |
| Missing search form | Devil's Advocate | Deterministic validation and exact follow-up retrieval |
| Final verdict | Code | Three-value decision function plus coverage state |
| Worker caller | Google-signed token | Signature, audience, email, verified email |
| Final writer | Current attempt | Firestore transaction compares `attempt_id` |

## Why both ADK tools and function nodes

ADK wraps the six deterministic callables as `FunctionTool` objects in `ToolRegistry`. The
orchestrator invokes those exact tool objects through `ctx.run_node` for normalization, expansion,
validation, retrieval, extraction, and verification. The orchestrator decides when each fact
tool runs instead of asking a model whether to call it. This keeps ADK load-bearing while keeping
exact retrieval outside model discretion.

## Job state

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> running: acquire lease
    running --> running: renew lease
    running --> queued: retryable failure
    running --> running: expired lease, new attempt
    running --> complete: Gate passed + CAS
    running --> failed: terminal delivery + CAS
    failed --> failed: late redelivery, no rerun
    complete --> [*]
    failed --> [*]
```

A message arriving during a valid lease receives non-2xx and is retried. A late worker can finish
its model call, but its final CAS fails if another `attempt_id` owns the job.
