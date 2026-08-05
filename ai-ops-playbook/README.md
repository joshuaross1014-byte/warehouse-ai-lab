# ai-ops-playbook

**How to give an AI assistant real access to production systems — and keep it safe.**

Most "AI for operations" writing stops at the demo. This is the part that comes after: the
connection layer, the safety model, the automation pipeline, the memory architecture, and the
operational discipline required to run it against systems that people depend on to do their jobs.

Written from experience building this pattern across a SAP Business One + Körber/HighJump WMS
estate — roughly a dozen database connections, a scheduled monitoring layer, and a diagnostic
skill library. **All identifiers, hostnames, accounts, schemas, and business volumes here are
generic or illustrative.** The value is the pattern, not the environment.

## The documents

| # | Document | What it covers |
|---|---|---|
| 01 | [MCP server pattern](01-mcp-server-pattern.md) | Complete source of the two server archetypes — read-write and fail-closed read-only — with the design decisions explained line by line |
| 02 | [Safety model](02-safety-model.md) | The layered defense model, why the write channel has *no* keyword filter, prompt-injection handling, and the AI failure modes you should expect |
| 03 | [Automation pipeline](03-automation-pipeline.md) | The nine-stage pipeline every automated task flows through, the automation lanes that ride on it, and criteria for what should *not* be automated |
| 04 | [Memory architecture](04-memory-architecture.md) | Eight layers of machine memory, the staleness rule that keeps them safe, and why capture must be cheap while recall must be verified |
| 05 | [Operating the stack](05-operating-the-stack.md) | Silent failure as the characteristic failure mode, the health check that catches it, and lessons from real outages |

## The core idea

An AI with database credentials is not a chatbot with extra features. It is a new kind of
operator — fast, tireless, occasionally confidently wrong, and completely dependent on the
guardrails you build around it.

Three principles run through everything here:

**Analyze broadly, write narrowly.** Read access can be generous because reads are recoverable.
Write access should be rare, deliberate, and gated. Most systems in a well-designed estate should
be structurally incapable of being written to by the AI at all.

**Policy travels with the tool.** A rule in a README is read once. A rule in a tool's docstring is
re-read by the model on every single call. Put your operating rules where they will actually be
delivered at the moment of use.

**Loud failures are safe failures.** The dangerous errors are not crashes — they are the quiet
ones: a plausible but wrong diagnosis, a stale fact recalled as current, a scheduled job that
reports success while doing nothing. Design so that failures announce themselves.

## Who this is for

Engineers who are past "should we use AI" and into "how do we run this without breaking
production." It assumes you can read Python and SQL, and that you own systems where a bad write
has consequences measured in shifts, not in tests.

---

*Part of [warehouse-ai-lab](../). Sanitized for public reference — see the note above.*
