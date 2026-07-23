# warehouse-ai-lab

AI applied to warehouse and ERP operations — a portfolio of self-contained projects, each with its own README, demo, and zero-to-minimal dependencies. Built from real experience running a SAP Business One + Körber (HighJump) WMS stack for a grocery distribution network.

| Project | What it is |
|---|---|
| [warehouse-twin](warehouse-twin/) | Digital twin of a grocery distribution center: zero-dependency discrete-event simulation grounded in real WMS operating statistics, with an AI scenario copilot on the roadmap. |
| [warehouse-aiops](warehouse-aiops/) | Self-healing warehouse operations with a human in the loop: detect → diagnose → propose → approve → execute → verify → runbook. Mock WMS included, AI console via MCP. |
| [sql-codebase-mcp](sql-codebase-mcp/) | Ask an AI "what breaks if I change this table?" Parses any SQL Server codebase into a dependency graph (calls/reads/writes) and serves it over MCP for instant impact analysis. |
| [claude-ops-toolkit](claude-ops-toolkit/) | AI-assisted ERP+WMS ops toolkit: Claude Code diagnostic skills plus always-on Windows Task Scheduler monitors with Slack alerts (sanitized reference). |
| [advantage-architect-mcp](advantage-architect-mcp/) | Develop a Körber/HighJump Advantage WMS's RF-gun screens, menus, and process flows directly in raw SQL over MCP — the reverse-engineered design-database object model, with Compile+Activate the only GUI step. |
| [kore-ui-mcp](kore-ui-mcp/) | Inspect and edit the Körber (HJ One) WMS web UI over MCP, plus the read-only-inspect + apply-in-editor workflow for the legacy WebWise (Access) pages. |

Most projects here were first developed in their own repository and merged with full commit history (`git log -- <project>/`).

## Common threads

- **MCP-first AI integration** — most of these projects expose their capabilities to AI assistants over the Model Context Protocol.
- **Stdlib-only where possible** — the simulations, graph parsing, and ops loops run on plain Python.
- **Grounded in production** — scenarios, statistics, and failure modes come from operating a real multi-DC WMS, sanitized for public reference.
