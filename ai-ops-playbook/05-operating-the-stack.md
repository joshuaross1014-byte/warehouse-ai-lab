# 05 — Operating the Stack

The failure mode that will actually bite you is not a crash. It is **silence**.

This document is about the operational discipline that keeps an AI-assisted stack honest: how these
systems fail quietly, the health check that makes failures loud, and the lessons that only show up
once you have run one for a while.

## Silent failure is the characteristic failure mode

Three properties of this architecture combine badly:

1. **A stdio MCP server that cannot launch produces no error.** It is a child process. If it dies
   on import — a moved file, a missing dependency, an absent credential — the client simply shows
   fewer tools. There is no alert, no log, no heartbeat. You notice weeks later when you reach for
   a tool that is not there.

2. **Windows Task Scheduler can report success for a job it never ran.** The default settings
   include *"do not start the task if the computer is running on batteries."* On a laptop, the
   scheduler will queue a job, quietly discard it, and record `LastTaskResult = 0`. The event log
   shows "launched" and "queued" but never "action started." Every dashboard says green.

3. **Config drift is invisible.** Move a project folder and every registration pointing at it
   breaks — client config, scheduled task working directories, indexer source roots. Nothing
   validates these at rest.

Combine them and you get a monitoring layer that has been dead for weeks while reporting success,
which is strictly worse than having no monitoring at all — because you believed it.

### Lessons learned the hard way

**Exit codes are not evidence of execution.** A scheduled job's exit status tells you what the
scheduler thinks happened. The only trustworthy signal is a side effect: did the log file get
written? Did the row appear? Check the artifact, not the status.

**"Registered" is not "working."** A config entry that references a valid-looking path proves
nothing. Verify by launching the thing and confirming it stays alive.

**Absence of alerts is not absence of problems.** If a monitor has been quiet for an unusual
stretch, the two explanations — "everything is fine" and "the monitor is dead" — look identical
from the outside. Design so you can tell them apart, e.g. by having monitors log a heartbeat on
clean runs, not only on alerts.

**Prefer absolute paths everywhere.** An interpreter referenced as bare `python` works until
something changes `PATH`, then fails in a way that looks like a completely different problem.

---

## The health check

One command that answers "is the stack actually working?" — scheduled daily, and deliberately
configured so battery state cannot block it.

```python
"""
ai_stack_healthcheck.py — makes silent failures loud.

Checks:
  A. Registration : every configured server -> does its script path exist?
  B. Launch       : can each server start and stay alive? (imports + creds OK)
  C. Monitors     : tasks exist, enabled, NOT battery-blocked, working directory
                    exists, and their LOG FILES are fresh
  D. Dependencies : pinned packages importable and at expected versions
  E. Index        : the document index exists, has content, sources resolve

Exit: 0 = healthy, 1 = warnings, 2 = failures
"""

def check_servers(config) -> None:
    for name, spec in sorted(config.get("mcpServers", {}).items()):
        cmd = [spec.get("command")] + list(spec.get("args") or [])
        script = cmd[-1] if len(cmd) > 1 else None

        # A. registration path resolves
        if not script or not os.path.exists(script):
            record("FAIL", f"mcp:{name}", f"script path missing -> {script}")
            continue

        # interpreter: absolute path preferred; PATH-resolved is a warning
        if not os.path.exists(cmd[0]):
            if shutil.which(cmd[0]):
                record("WARN", f"mcp:{name}",
                       f"interpreter '{cmd[0]}' resolves via PATH only")
            else:
                record("FAIL", f"mcp:{name}", f"interpreter missing -> {cmd[0]}")
                continue

        # B. does it actually start? a crash on import exits immediately
        p = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                             text=True, cwd=os.path.dirname(script))
        time.sleep(3.0)
        if p.poll() is None:
            p.kill(); p.communicate(timeout=5)
            record("OK", f"mcp:{name}")
        else:
            out, err = p.communicate(timeout=5)
            tail = (err or out or "").strip().splitlines()
            record("FAIL", f"mcp:{name}", tail[-1][:120] if tail else "exited immediately")


def check_monitors() -> None:
    for task, (script, logfile, max_age_h) in MONITORS.items():
        xml = export_scheduled_task(task)

        # the two silent-failure causes, checked explicitly
        if "<DisallowStartIfOnBatteries>true" in xml:
            record("FAIL", f"monitor:{task}",
                   "battery-blocked: will not run on battery")

        wd = extract(xml, "WorkingDirectory")
        if wd and not os.path.isdir(wd):
            record("FAIL", f"monitor:{task}", f"working directory missing -> {wd}")

        # freshness of the LOG is the real proof it ran -- not the exit code
        age_h = (time.time() - os.path.getmtime(log_path(logfile))) / 3600.0
        if age_h > max_age_h:
            record("WARN", f"monitor:{task}", f"log {age_h:.0f}h old")
        else:
            record("OK", f"monitor:{task}", f"log {age_h:.1f}h old")
```

The design choices that make it useful:

- **It launches every server** rather than just checking that paths exist. Import errors and
  missing credentials only show up when the process actually starts.
- **It judges monitors by log freshness**, never by scheduler exit code — the specific trap that
  hides battery-blocked jobs.
- **It checks for battery-blocking explicitly**, because that setting is a default and silently
  disables scheduled work on any laptop.
- **It verifies index source roots resolve**, catching config drift before it silently shrinks
  what search can find.
- **It distinguishes warnings from failures** with different exit codes, so it can be wired into
  anything that reacts to exit status.

### Pin your dependencies

Every server in the estate shares one toolchain. An unnoticed upgrade of the protocol library or a
database driver changes every server at once, and the failure is silent. A pinned requirements file
plus a dedicated virtual environment turns an invisible break into a deliberate decision.

```
mcp==<pinned>              # protocol layer — shared by every server
pyodbc==<pinned>           # SQL Server driver
SQLAlchemy==<pinned>       # engine/transaction handling
hdbcli==<pinned>           # SAP HANA driver
requests==<pinned>         # REST integrations
```

Treat a toolchain upgrade as a change to be validated — run the health check afterward — not as
routine maintenance.

---

## Continuity

Questions worth answering before you need the answers.

**What keeps running without the person who built it?** In a well-designed setup: everything
operational. Deployed fixes live in the database and run on their own. The AI layer accelerates
engineering; it should never be a runtime dependency of operations. If the answer to this question
is "the warehouse stops," the architecture is wrong.

**What stops?** Diagnostic skills, the development loop, and anything requiring the credentials —
which are per-person by design. Scheduled monitors keep firing but nobody reads the output.

**What is model-dependent?** Less than people assume:

| Asset | Model-dependent? |
|---|---|
| The MCP servers | No — plain Python, usable by any MCP-capable client |
| Deployed SQL and design objects | No — running in the database; the AI's involvement ended at authoring |
| Skills, instruction files, runbooks, issue log | Mostly no — markdown that any capable model reads |
| Document index | Partly — embeddings are model-specific; a change means re-indexing, not re-collecting |
| Quality of diagnosis and judgment | **Yes** — which is exactly why the human gate exists regardless of model |

The durable core is large. If the vendor vanished tomorrow, every deployed fix keeps running, every
server works with another client, and all knowledge stays readable. What would be lost is the
*acceleration*, not the *assets*. That is the right architecture for a program built on
fast-moving technology.

**Where does knowledge live?** If the answer is "on one workstation," fix that first. Documents,
skills, and runbooks belong somewhere version-controlled and shared. This is the cheapest
continuity insurance available and the one most often skipped.

---

## A short operational checklist

- [ ] Every server registered with an **absolute** interpreter and script path
- [ ] A health check running on a schedule, and **not battery-blocked**
- [ ] Monitors judged by log freshness, not exit codes
- [ ] Monitors that log a heartbeat on clean runs, so silence is distinguishable from success
- [ ] Dependencies pinned; toolchain upgrades validated
- [ ] Rollback saved *before* each production change
- [ ] Write audit at the database layer, so the confirmation rule is verifiable
- [ ] Knowledge assets backed up off the workstation
- [ ] Index source roots verified after any folder reorganization
- [ ] A second person who can run the stack

---

*Back to the [playbook index](README.md).*
