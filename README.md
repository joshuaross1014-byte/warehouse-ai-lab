# warehouse-ai-lab

AI applied to warehouse and ERP operations — a portfolio of four self-contained projects, each with its own README, demo, and zero-to-minimal dependencies. Built from real experience running a SAP Business One + Körber (HighJump) WMS stack for a grocery distribution network.

| Project | What it is |
|---|---|
| [warehouse-twin](warehouse-twin/) | Digital twin of a grocery distribution center: zero-dependency discrete-event simulation grounded in real WMS operating statistics, with an AI scenario copilot on the roadmap. |
| [warehouse-aiops](warehouse-aiops/) | Self-healing warehouse operations with a human in the loop: detect → diagnose → propose → approve → execute → verify → runbook. Mock WMS included, AI console via MCP. |
| [sql-codebase-mcp](sql-codebase-mcp/) | Ask an AI "what breaks if I change this table?" Parses any SQL Server codebase into a dependency graph (calls/reads/writes) and serves it over MCP for instant impact analysis. |
| [claude-ops-toolkit](claude-ops-toolkit/) | AI-assisted ERP+WMS ops toolkit: Claude Code diagnostic skills plus always-on Windows Task Scheduler monitors with Slack alerts (sanitized reference). |

Each project was developed in its own repository and merged here with full commit history (`git log -- <project>/`).

## Common threads

- **MCP-first AI integration** — three of the four projects expose their capabilities to AI assistants over the Model Context Protocol.
- **Stdlib-only where possible** — the simulations, graph parsing, and ops loops run on plain Python.
- **Grounded in production** — scenarios, statistics, and failure modes come from operating a real multi-DC WMS, sanitized for public reference.
