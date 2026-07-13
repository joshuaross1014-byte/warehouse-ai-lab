# warehouse-aiops

**Self-healing warehouse operations with a human in the loop.** A monitor that pages you
is nice; this closes the rest of the incident lifecycle:

```
DETECT ──> DIAGNOSE ──> PROPOSE ──> [ HUMAN APPROVES ] ──> EXECUTE ──> VERIFY ──> RUNBOOK
(read-only) (read-only)  (data,                            (transaction,  (read-back,
                          never action)                     rollback-safe)  or it didn't happen)
```

Built from running AI-assisted operations against a real ERP + WMS landscape — the
companion to [claude-ops-toolkit](https://github.com/joshuaross1014-byte/claude-ops-toolkit)
(detection) and [warehouse-twin](https://github.com/joshuaross1014-byte/warehouse-twin)
(simulation): **detect → simulate → act.**

## The safety model (the whole point)

Automating production fixes is easy; automating them *safely* is the discipline:

1. **Detection and diagnosis are read-only.** Always.
2. **A proposal is data, not an action** — the exact SQL, a verification contract
   (query + expected result), and an explicit risk note. It sits in PROPOSED until a human decides.
3. **Execution only on explicit approval**, inside a transaction, immediately verified by
   read-back — a verification mismatch rolls back and the incident goes to FAILED.
4. **Knowing what NOT to automate is a feature.** The `import_error` playbook deliberately
   proposes a *manual* path: bad master data must be fixed upstream, and auto-"fixing" it
   would mask the root cause. Manual incidents are ACKNOWLEDGED (no re-alerting) and
   auto-close when a scan confirms the upstream fix landed.
5. **Every outcome appends to the runbook** — the organizational memory that makes the next
   diagnosis (human or AI) faster.

## Try it in 60 seconds (stdlib only, mock warehouse included)

```bash
python aiops.py seed        # mock WMS with seeded faults
python aiops.py scan
# [CRITICAL] INC-0001  3 order import(s) stuck in-progress > 15 min
#            proposal (sql_fix): Reset 3 stuck row(s) to NULL so the next cycle retries
# [WARNING ] INC-0002  Order 500023 failed import: Invalid Warehouse ID on Outbound Order
#            proposal (manual): fix the warehouse mapping upstream, then re-export

python aiops.py show INC-0001      # full evidence, diagnosis, exact SQL, risk, verify contract
python aiops.py approve INC-0001   # INC-0001 -> VERIFIED: fix executed and verified (3 rows)
python aiops.py approve INC-0002   # -> ACKNOWLEDGED (manual path; no re-alerting)
python aiops.py scan               # clean — dedup + acknowledgement hold
python aiops.py runbook            # the postmortem trail
```

The mock (`mock/seed.py`) mirrors the *shape* of a real host-integration layer with seeded
faults: a crashed importer leaving rows claimed mid-batch, and a genuine import error hiding
among benign lock rejections (the WMS correctly refusing to modify in-flight orders — the
detector strips those and alerts only on the residual).

## AI layer

`aiops_mcp_server.py` exposes the loop to an AI assistant (MCP): `scan_now`,
`list_incidents`, `get_incident`, `approve_incident`, `reject_incident`, `read_runbook`.
The assistant becomes the incident console — it explains diagnoses, compares against runbook
history, and executes a decision **only when the human explicitly makes it** (the approval
tools carry that governance in their contract).

```bash
claude mcp add warehouse_aiops -s user -- python /path/to/aiops_mcp_server.py
# then: "scan the warehouse and walk me through anything you find"
```

## Architecture

```
playbooks/    one incident type per file: detect() / diagnose() / propose()
core/         models (state machine) · store (SQLite + fingerprint dedup) · engine (the loop)
mock/         seeded mock WMS so the demo runs anywhere
aiops.py      CLI: seed · scan · list · show · approve · reject · runbook
aiops_mcp_server.py   the AI interface
```

Adding a playbook = one file with three functions + a registry line. Pointing at a real
warehouse = swapping the connection in one place (the private, production version of this
runs against a live WMS through the same interface).

## Provenance & sanitization

Patterns, benign-error phrases, and fault scenarios come from operating a real multi-site
grocery WMS; everything here is generic (mock schema, generic names, seeded data). No
endpoints, credentials, schemas, or business data.

## Roadmap

- [x] v0.1 — the full loop, two playbooks, mock WMS, CLI, MCP layer
- [ ] Slack approvals (post proposal, approve from the thread)
- [ ] Scheduled scans (Task Scheduler/cron) with exception-only notification
- [ ] More playbooks: serial-completeness quarantine, order-flow drift, price-gap
- [ ] Runbook-aware diagnosis: feed history back into classification

## Author

Joshua Ross — ERP & WMS systems analyst (SAP Business One, Körber/Infios HighJump/KCloud),
B.S.E. Industrial Engineering.
