"""
agent.py - a standalone, read-only WMS assistant on the Claude API.

    python agent.py                      interactive (type a question, Ctrl+C or 'quit' to leave)
    python agent.py --ask "question"     one question, answer, exit
    python agent.py --dry-run            show the system prompt size and the tools; no API call

What it is
    The same specialised assistant you get in Claude Code (wms-knowledge skill + cheat
    sheet + the WMS tools), packaged so it can run without Claude Code: from a script,
    a scheduled job, or later behind a chat bot. Claude Opus 5.5 by default, adaptive
    thinking, streamed output, prompt caching on the fixed context, and the SDK tool
    runner driving the tool loop.

Safety
    Every tool is read-only by construction (guard.py). There is nothing to approve
    because nothing can write. Questions and tool results are sent to the Claude API;
    keep personal data and secrets out of questions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time

import anthropic

# Windows consoles default to a legacy code page; WMS data and docs carry non-ASCII text.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config  # noqa: E402
import tools   # noqa: E402

SYSTEM_RULES = """You are the WMS assistant for a Körber/HighJump Advantage warehouse management system on SQL Server. You answer questions about warehouse behaviour, data, procedures and integrations for the WMS engineering team and warehouse supervisors.

Operating rules
- You are READ-ONLY. Your run_sql tool refuses anything but a single SELECT. Never claim to have changed anything. When a fix needs a write, give the exact SQL and the verification query and say that a person must run it through the normal confirm-and-backup path.
- Lookup order: read_reference for the matching domain file first when the question touches WMS behaviour or design; recall / schema / object_definition from the memory bank next (cheap, cached) when those tools exist; run_sql against the live server for current data or anything the person will act on; search_knowledge for past fixes, runbooks and design documents when it exists.
- Verify before asserting. Facts in the references carry a verified date; if the question is about current state, check live. Never present a cached count as current.
- SQL conventions: the tool runs under READ UNCOMMITTED, so WITH (NOLOCK) is optional. Use TOP and date filters on t_tran_log, t_pick_detail, t_stored_item, t_al_host_*. Check column names before guessing; column names differ between tables.
- Answers: lead with the answer, then the evidence (which query, which table, how many rows). Name objects exactly. State facts and next actions neutrally; never describe a problem as "a system issue" or assign blame. Mark anything unverified as "needs confirmation".
- If a tool returns an error, say so and try a different approach; do not invent results.
- The default server is {default_server}. Servers: {servers}. A production server is production whatever it is called.
"""


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip()
    return text


def _cheat_sheet(claude_md: str) -> str:
    start = claude_md.find("## WMS cheat sheet")
    if start == -1:
        return ""
    rest = claude_md[start:]
    nxt = rest.find("\n## ", 5)
    return rest if nxt == -1 else rest[:nxt]


def build_system() -> list[dict]:
    """Static context, cached for an hour. Nothing volatile goes in here (dates go in the user turn)."""
    skill = ""
    if config.SKILL_DIR is not None:
        skill = _strip_frontmatter(config.SKILL_DIR.joinpath("SKILL.md").read_text(encoding="utf-8"))
    cheat = _cheat_sheet(config.CLAUDE_MD.read_text(encoding="utf-8")) if config.CLAUDE_MD.exists() else ""
    servers = ", ".join(f"{n} ({s.get('host')}/{s.get('db')}, {'PRODUCTION' if s.get('production') else 'test'})"
                        for n, s in sorted(config.SERVERS.items()))
    rules = SYSTEM_RULES.format(default_server=config.DEFAULT_SERVER, servers=servers)
    text = rules
    if skill:
        text += "\n\n# Domain knowledge index (use read_reference to load a file)\n\n" + skill
    if cheat:
        text += "\n\n# Cheat sheet\n\n" + cheat
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]


def _cost(usage, model: str) -> str:
    p = config.PRICES.get(model)
    if not p:
        return ""
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    usd = (inp * p["in"] + out * p["out"] + cr * p["cache_read"] + cw * p["in"] * 1.25) / 1e6
    return f"in {inp} | cache read {cr} | cache write {cw} | out {out} | ~${usd:.4f}"


class Session:
    def __init__(self, model: str, effort: str, default_server: str, verbose: bool = True):
        self.client = anthropic.Anthropic()          # ANTHROPIC_API_KEY from the environment
        self.model = model
        self.effort = effort
        self.verbose = verbose
        config.DEFAULT_SERVER = default_server
        self.system = build_system()
        self.tools = tools.all_tools()
        self.history: list[dict] = []
        self.started = dt.datetime.now()
        config.TRANSCRIPT_DIR.mkdir(exist_ok=True)
        self.transcript = config.TRANSCRIPT_DIR / f"{self.started:%Y-%m-%d}.jsonl"

    def _runner_kwargs(self) -> dict:
        kw = dict(
            model=self.model,
            max_tokens=config.MAX_TOKENS,
            system=self.system,
            tools=self.tools,
            messages=self.history,
            stream=True,
            max_iterations=config.MAX_ITERATIONS,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral", "ttl": "1h"},   # grows with the conversation tail
        )
        if config.FALLBACKS_ON:
            kw["betas"] = ["server-side-fallback-2026-07-01"]
            kw["fallbacks"] = "default"
        return kw

    def ask(self, question: str) -> str:
        today = dt.date.today().isoformat()
        user_text = f"(Today is {today}.) {question}" if not self.history else question
        self.history.append({"role": "user", "content": user_text})
        turn = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "question": question,
                "tool_calls": [], "answer": "", "usage": [], "stop_reason": None}
        t0 = time.perf_counter()
        final_text_parts: list[str] = []
        attempts = 0
        while True:
            attempts += 1
            try:
                final_text_parts = self._run_once(turn)
                break
            except ValueError as exc:            # eager-streamed tool input that could not be parsed
                if attempts >= 2:
                    raise
                print(f"\n[retrying: unparseable tool input from the stream: {exc}]", file=sys.stderr)
        answer = "".join(final_text_parts).strip()
        turn["answer"] = answer
        turn["seconds"] = round(time.perf_counter() - t0, 1)
        with self.transcript.open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn, ensure_ascii=False) + "\n")
        return answer

    def _run_once(self, turn: dict) -> list[str]:
        runner = self.client.beta.messages.tool_runner(**self._runner_kwargs())
        parts: list[str] = []
        for stream in runner:
            parts = []                                   # only the last assistant turn is the answer
            for event in stream:
                if event.type == "text":
                    parts.append(event.text)
                    if self.verbose:
                        print(event.text, end="", flush=True)
                elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                    if self.verbose:
                        print(f"\n  > {event.content_block.name} ...", flush=True)
            message = stream.get_final_message()
            for block in message.content:
                if block.type == "tool_use":
                    turn["tool_calls"].append({"tool": block.name, "input": block.input})
                elif block.type == "fallback":
                    print(f"\n[{block.from_.model} declined; {block.to.model} continued]", file=sys.stderr)
            turn["usage"].append(_cost(message.usage, self.model))
            turn["stop_reason"] = message.stop_reason
            # mirror the history so the next question continues the conversation
            self.history.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                self.history.append(tool_response)
            if message.stop_reason == "refusal":
                d = message.stop_details
                parts.append(f"\n[The model declined this request"
                             f"{' (' + d.category + ')' if d and getattr(d, 'category', None) else ''}.]")
                break
            if message.stop_reason == "max_tokens":
                parts.append("\n[Answer cut off at the token ceiling; ask a narrower question.]")
        if self.verbose:
            print()
            print(f"  [{self.model} | {turn['usage'][-1] if turn['usage'] else ''} | {len(turn['tool_calls'])} tool calls]")
        return parts


def dry_run(model: str, effort: str, default_server: str) -> None:
    config.DEFAULT_SERVER = default_server
    system = build_system()
    text = system[0]["text"]
    print(f"model {model}, effort {effort}, default server {default_server}")
    print(f"system prompt: {len(text):,} chars (~{len(text)//4:,} tokens), cached 1h")
    print(f"servers: {', '.join(config.SERVERS)}")
    print(f"skill:       {config.SKILL_DIR or 'not found'}")
    print(f"memory bank: {config.MEMORY_DIR or 'not configured (memory tools skipped)'}")
    print(f"knowledge:   {config.KNOWLEDGE_DIR or 'not configured (search_knowledge skipped)'}")
    print("tools:")
    for t in tools.all_tools():
        print(f"  - {t.name}")
    print("fallbacks:", "on (server-side-fallback-2026-07-01, default)" if config.FALLBACKS_ON else "off")


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only WMS assistant on the Claude API")
    ap.add_argument("--ask", help="one question, then exit")
    ap.add_argument("--model", default=config.MODEL)
    ap.add_argument("--effort", default=config.EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--server", default=config.DEFAULT_SERVER, choices=sorted(config.SERVERS),
                    help="server Claude queries unless told otherwise")
    ap.add_argument("--dry-run", action="store_true", help="print the system prompt size and tools; no API call")
    ap.add_argument("--quiet", action="store_true", help="print only the final answer")
    a = ap.parse_args()

    if a.dry_run:
        dry_run(a.model, a.effort, a.server)
        return 0
    try:
        session = Session(a.model, a.effort, a.server, verbose=not a.quiet)
    except anthropic.AuthenticationError:
        print("ANTHROPIC_API_KEY is missing or invalid. Set it as an environment variable or in agent/.env.")
        return 2
    try:
        if a.ask:
            answer = session.ask(a.ask)
            if a.quiet:
                print(answer)
            return 0
        print(f"WMS assistant ({a.model}, effort {a.effort}, default server {a.server}). 'quit' to exit.\n")
        while True:
            try:
                q = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q:
                continue
            if q.lower() in ("quit", "exit", "q"):
                break
            session.ask(q)
            print()
        return 0
    except anthropic.AuthenticationError:
        print("ANTHROPIC_API_KEY is missing or invalid. Set it as an environment variable or in agent/.env.")
    except anthropic.RateLimitError as exc:
        print(f"Rate limited; retry after {exc.response.headers.get('retry-after', '60')} s.")
    except anthropic.APIStatusError as exc:
        print(f"API error {exc.status_code}: {exc.message} (request {getattr(exc, 'request_id', '?')})")
    except anthropic.APIConnectionError:
        print("Cannot reach the Claude API. Check the network or proxy.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
