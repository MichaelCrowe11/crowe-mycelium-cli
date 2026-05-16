#!/usr/bin/env python3
"""Crowe Mycelium CLI.

A focused, single-model CLI that hosts Gemma 4 Mycelium — Crowe Logic's first
open-source model, built on Google Gemma 4.

Commands:
    crowe-mycelium                # interactive chat (default)
    crowe-mycelium chat           # interactive chat (explicit)
    crowe-mycelium run "prompt"   # one-shot
    crowe-mycelium info           # model + backend status
    crowe-mycelium models         # list registered model (currently 1)
"""

from __future__ import annotations

import sys
from typing import Optional

import click
from rich.table import Table
from rich import box

from crowe_mycelium import __version__
from crowe_mycelium import branding
from crowe_mycelium.branding import console
from crowe_mycelium.model import (
    check_backend,
    load_model_spec,
    load_system_prompt,
    ollama_host,
    ollama_tag,
    stream_chat,
)


def _build_messages(history: list[tuple[str, str]], system: str, user_msg: str) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": system}]
    for role, content in history:
        msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_msg})
    return msgs


def _chat_loop(temperature: float) -> None:
    spec = load_model_spec()
    system = load_system_prompt()

    ok, msg = check_backend()
    branding.welcome(
        model_label=spec.label,
        base_model=spec.base_model,
        backend_label=msg,
    )
    if not ok:
        branding.error(msg)
        branding.info("Start Ollama (`ollama serve`) and pull the model, then retry.")
        sys.exit(1)

    history: list[tuple[str, str]] = []
    while True:
        try:
            user_msg = console.input(branding.user_prefix() + "› ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not user_msg:
            continue
        if user_msg in {"/quit", "/exit", ":q"}:
            break
        if user_msg == "/help":
            branding.info("/quit · /reset · /info · anything else is a prompt")
            continue
        if user_msg == "/reset":
            history.clear()
            branding.info("conversation cleared.")
            continue
        if user_msg == "/info":
            _print_info(spec)
            continue

        messages = _build_messages(history, system, user_msg)
        console.print(branding.model_prefix(spec.label) + "›", end=" ")
        reply_parts: list[str] = []
        try:
            for chunk in stream_chat(messages, temperature=temperature):
                console.print(chunk, end="", soft_wrap=True, highlight=False)
                reply_parts.append(chunk)
            console.print()
        except Exception as e:
            console.print()
            branding.error(f"generation failed: {e}")
            continue

        history.append(("user", user_msg))
        history.append(("assistant", "".join(reply_parts)))

    branding.attribution_footer()


def _print_info(spec) -> None:
    table = Table(box=box.SIMPLE_HEAVY, show_header=False, pad_edge=False)
    table.add_column("k", style="grey50")
    table.add_column("v", style="white")
    table.add_row("model", spec.name)
    table.add_row("label", spec.label)
    table.add_row("base", f"{spec.base_model} (Gemma 4)")
    table.add_row("ollama tag", ollama_tag())
    table.add_row("ollama host", ollama_host())
    table.add_row("context", str(spec.context_window))
    table.add_row("license", f"{spec.license}  ·  {spec.license_url}")
    console.print(table)


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="crowe-mycelium")
@click.option("--temperature", "-t", default=0.4, show_default=True, type=float,
              help="Sampling temperature for chat/run.")
@click.pass_context
def main(ctx: click.Context, temperature: float) -> None:
    """Crowe Mycelium — offline cultivation intelligence built on Gemma 4."""
    ctx.ensure_object(dict)
    ctx.obj["temperature"] = temperature
    if ctx.invoked_subcommand is None:
        _chat_loop(temperature)


@main.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Start an interactive chat session."""
    _chat_loop(ctx.obj["temperature"])


@main.command()
@click.argument("prompt", nargs=-1, required=True)
@click.pass_context
def run(ctx: click.Context, prompt: tuple[str, ...]) -> None:
    """Run a single prompt and stream the answer to stdout."""
    spec = load_model_spec()
    system = load_system_prompt()
    ok, msg = check_backend()
    if not ok:
        branding.error(msg)
        sys.exit(1)
    user_msg = " ".join(prompt)
    messages = _build_messages([], system, user_msg)
    for chunk in stream_chat(messages, temperature=ctx.obj["temperature"]):
        sys.stdout.write(chunk)
        sys.stdout.flush()
    sys.stdout.write("\n")


@main.command()
def info() -> None:
    """Show model and backend status."""
    spec = load_model_spec()
    ok, msg = check_backend()
    _print_info(spec)
    if ok:
        console.print(f"[bright_green]backend ok[/] · {msg}")
    else:
        console.print(f"[bold red]backend down[/] · {msg}")
    branding.attribution_footer()


@main.command()
def models() -> None:
    """List registered models (single-model CLI, currently 1)."""
    spec = load_model_spec()
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("name", style="bold")
    table.add_column("label")
    table.add_column("base")
    table.add_column("family")
    table.add_row(spec.name, spec.label, spec.base_model, "crowe-logic")
    console.print(table)
    branding.attribution_footer()


if __name__ == "__main__":
    main()
