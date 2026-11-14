#!/usr/bin/env python3

"""
icutwin-tokenize: CLIF tables -> clinically aware token timelines
"""

import pathlib
import time
from typing import Annotated, Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from icutwin.tokenizer import assembly
from icutwin.tokenizer.helpers import ClifData, Vocabulary, load_spec, spec_hash

app = typer.Typer(
    name="icutwin-tokenize",
    help="Clinically aware CLIF tokenizer with a fixed vocabulary",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
console = Console()

OUT = pathlib.Path("tokenized_output")  # under the folder the command runs from
ConfigArg = Annotated[
    pathlib.Path, typer.Argument(help="config yaml: clif_path, timezone + run options")
]


def show_step(s: dict):
    """one line per CLIF table step: tokens, spec codes found, what is missing"""
    found = s["codes"] - len(s["missing"])
    mark = "[red]✗[/red]" if s["missing_tables"] else "[green]✓[/green]"
    line = f"  {mark} {s['step']:<30} {s['tokens']:>12,} tokens"
    line += f"  {found}/{s['codes']} codes"
    if s["missing_tables"]:
        line += f"  [red]table not found: {', '.join(s['missing_tables'])}[/red]"
    for t, cols in s["missing_columns"].items():
        line += f"  [yellow]{t} lacks columns: {', '.join(cols)}[/yellow]"
    if s["missing"]:
        line += f"\n      [yellow]missing: {', '.join(s['missing'])}[/yellow]"
    console.print(line, highlight=False)


@app.command()
def pipeline(config: ConfigArg):
    """Build every table, split the stays, then write the token timelines."""
    t0 = time.perf_counter()
    clif, out = ClifData(config), OUT.resolve()
    print(f"\n[bold]CLIF data[/bold] ({clif.tz}) {clif.raw_data_home}")
    with console.status("[bold green]Collating table by table..."):
        qc = assembly.collate(clif, out, report=show_step)
    tot = qc["totals"]
    print(f"  {tot['tokenized']:,} / {tot['rows']:,} values tokenized")
    if qc["high_drop_rate"]:
        print(
            f"  [yellow]{len(qc['high_drop_rate'])} variables drop >5%; "
            "see qc_report.json[/yellow]"
        )
    n = assembly.split(clif, out)
    print(
        f"\nRandom split, seed {clif.cfg.split.seed}: train {n['train']:,} / "
        f"tuning {n['tuning']:,} / held_out {n['held_out']:,}"
    )
    with console.status("[bold green]Tokenizing..."):
        qc = assembly.tokenize(clif, out)
    sp = qc["split"]
    print(
        f"  {qc['short_stays_removed']:,} short stays removed; "
        f"train {sp['train']:,} / tuning {sp['tuning']:,} / "
        f"held_out {sp['held_out']:,} stays"
    )
    print(f"  Output: [cyan]{out}[/cyan]")
    dt = time.perf_counter() - t0
    print(f"\n[bold green]Pipeline completed in {dt:.2f}s.[/bold green]")


@app.command()
def table(
    config: ConfigArg,
    step: Annotated[
        str, typer.Argument(help="table to build: " + ", ".join(assembly.STEPS))
    ],
):
    """Build one table on its own (debug): tables/<step>.parquet and .json."""
    if step not in assembly.STEPS:
        raise typer.BadParameter(f"{step!r}; one of {', '.join(assembly.STEPS)}")
    out = OUT.resolve()
    show_step(assembly.run_table(ClifData(config), out, step))
    print(f"  Output: [cyan]{out / 'tables' / step}.parquet[/cyan]")


@app.command("validate-spec")
def validate_spec():
    """Validate the shipped token spec and summarize it."""
    spec = load_spec()
    vocab = Vocabulary(spec)
    unreviewed = [c.code for c in spec.continuous if not c.reviewed]
    print(
        f"[green]✓[/green] spec v{spec.spec_version} (CLIF {spec.clif_version}) "
        f"sha256 {spec_hash()[:12]} is valid"
    )
    print(
        f"  {len(spec.continuous)} continuous, {len(spec.ordinal)} ordinal, "
        f"{len(spec.categorical)} categorical variables; {len(vocab)} tokens"
    )
    if unreviewed:
        print(
            f"  [yellow]{len(unreviewed)} plausible ranges await clinical review:"
            f"[/yellow] {', '.join(unreviewed)}"
        )


@app.command()
def vocab(
    grep: Annotated[Optional[str], typer.Argument(help="substring filter")] = None,
):
    """Print the fixed vocabulary with each token's clinical meaning."""
    v = Vocabulary()
    table = Table("id", "token", "meaning")
    for w, i in v.lookup.items():
        if grep is None or grep.lower() in w.lower():
            table.add_row(str(i), w, v.descriptions.get(w, ""))
    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
