"""Command-line interface for the Trade Intelligence Copilot.

    copilot ask "What was total net revenue in the West region for Q4 2024?"
    copilot eval            # run all 10 Part A questions, write a results report
    copilot build-db        # (re)build the DuckDB file from the CSVs
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import OUTPUTS_DIR, settings
from .db import Database
from .eval_questions import load_eval_questions

app = typer.Typer(add_completion=False, help="Trade Intelligence Copilot")
console = Console()


def _render(result: dict) -> None:
    status = result["status"]
    color = {"answered": "green", "clarify": "yellow", "refused": "red",
             "error": "red"}.get(status, "white")
    console.print(Panel(result["answer"], title=f"[{color}]{status.upper()}[/] · route={result['route']}",
                        border_style=color))
    if result.get("sql"):
        console.print(Panel(result["sql"], title="SQL", border_style="blue"))
    if result.get("citations"):
        console.print(f"[dim]Sources:[/] {', '.join(result['citations'])}")
    console.print(f"[dim]Trace:[/] {' → '.join(result.get('trace', []))}")


@app.command()
def ask(question: str, max_retries: int = 1) -> None:
    """Ask the copilot a single question."""
    from .agent import build_agent, run_agent

    if not settings.has_real_api_key:
        console.print("[yellow]No ANTHROPIC_API_KEY set — using offline deterministic stub.[/]")
    agent, _ = build_agent(max_retries=max_retries)
    _render(run_agent(question, agent))


@app.command()
def eval(out: Path = typer.Option(OUTPUTS_DIR / "part_a_results.md", help="Report path")) -> None:
    """Run the full Part A evaluation (10 questions) and write a report."""
    from .agent import build_agent, run_agent

    if not settings.has_real_api_key:
        console.print("[yellow]No ANTHROPIC_API_KEY set — using offline deterministic stub.[/]")
    agent, _ = build_agent()
    questions = load_eval_questions()

    table = Table(title="Part A — Evaluation", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Status")
    table.add_column("Question", max_width=42)
    table.add_column("Answer / first row", max_width=46)

    results = []
    for i, q in enumerate(questions, 1):
        r = run_agent(q, agent)
        results.append(r)
        short = r["answer"].splitlines()[0][:80]
        table.add_row(str(i), r["status"], q[:60], short)
    console.print(table)

    _write_report(out, results)
    console.print(f"[green]Report written to {out}[/]")


def _write_report(out: Path, results: list[dict]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Part A — Evaluation Results\n",
             "Each question with its routing decision, answer, generated SQL, and sources.\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"## Q{i}. {r['question']}\n")
        lines.append(f"- **Status / route:** {r['status']} / {r['route']}")
        if r.get("route_reason"):
            lines.append(f"- **Routing reason:** {r['route_reason']}")
        lines.append(f"- **Answer:**\n\n```\n{r['answer']}\n```")
        if r.get("sql"):
            lines.append(f"- **SQL:**\n\n```sql\n{r['sql']}\n```")
        if r.get("citations"):
            lines.append(f"- **Sources:** {', '.join(r['citations'])}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


@app.command("build-db")
def build_db() -> None:
    """(Re)build the DuckDB file from the CSV exports."""
    db = Database().build(force=True)
    schema = db.schema()
    console.print(f"[green]Built {db.db_path}[/] with {len(schema)} tables.")


if __name__ == "__main__":
    app()
