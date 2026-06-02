#!/usr/bin/env python3
"""Crowe Mycelium CLI — cultivation intelligence on Gemma 4 Mycelium.

Backends: local Ollama, Modal cloud, or auto (cloud-first → local fallback).

    crowe-mycelium                      # interactive chat (default)
    crowe-mycelium --local chat         # force local
    crowe-mycelium run "prompt"         # one-shot (plain when piped)
    crowe-mycelium info | models | doctor
"""

from __future__ import annotations

import sys

import click
from dotenv import load_dotenv
from rich import box
from rich.table import Table

from crowe_mycelium import __version__, branding
from crowe_mycelium.backends import build_backend
from crowe_mycelium.branding import console
from crowe_mycelium.config import resolve_settings
from crowe_mycelium.model import load_model_spec, load_system_prompt, ollama_host, ollama_tag
from crowe_mycelium.render.plain import PlainRenderer
from crowe_mycelium.render.rich import RichRenderer
from crowe_mycelium.session import dispatch_slash


def _settings(ctx):
    return resolve_settings(backend=ctx.obj.get("backend"), temperature=ctx.obj["temperature"])


def _build_messages(history, system, user_msg):
    msgs = [{"role": "system", "content": system}]
    for role, content in history:
        msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_msg})
    return msgs


def _print_info(spec, settings) -> None:
    table = Table(box=box.SIMPLE_HEAVY, show_header=False, pad_edge=False)
    table.add_column("k", style="grey50")
    table.add_column("v", style="white")
    table.add_row("model", spec.name)
    table.add_row("label", spec.label)
    table.add_row("base", f"{spec.base_model} (built with Gemma)")
    table.add_row("backend", settings.backend)
    table.add_row("cloud app", settings.cloud_app)
    table.add_row("ollama tag", ollama_tag())
    table.add_row("ollama host", ollama_host())
    table.add_row("context", str(spec.context_window))
    console.print(table)


def _chat_loop(ctx) -> None:
    settings = _settings(ctx)
    backend = build_backend(settings)
    system = load_system_prompt()
    renderer = RichRenderer()

    console.print(branding.hero(getattr(backend, "label", settings.backend)))
    history: list[tuple[str, str]] = []
    while True:
        try:
            tag = branding.backend_tag(getattr(backend, "label", settings.backend))
            user_msg = console.input(f"{tag} {branding.user_prefix()}▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not user_msg:
            continue

        res = dispatch_slash(user_msg)
        if res.handled:
            if res.action == "quit":
                break
            if res.action == "help":
                branding.info("/local /cloud /auto · /info /reset /doctor /quit")
            elif res.action == "reset":
                history.clear()
                branding.info("conversation cleared.")
            elif res.action == "info":
                _print_info(load_model_spec(), settings)
            elif res.action == "doctor":
                _doctor_report(settings)
            elif res.action == "switch":
                settings = resolve_settings(backend=res.arg, temperature=settings.temperature)
                backend = build_backend(settings)
                branding.info(f"switched to {res.arg}.")
            else:
                branding.info("unknown command. /help")
            continue

        messages = _build_messages(history, system, user_msg)
        try:
            reply = renderer.render_stream(backend.stream_chat(messages, settings.temperature))
        except Exception as e:
            renderer.error(str(e))
            continue
        history.append(("user", user_msg))
        history.append(("assistant", reply))

    branding.footer()


def _doctor_report(settings) -> None:
    from crowe_mycelium.backends.local import LocalOllamaBackend

    local = LocalOllamaBackend()
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("backend")
    table.add_column("status")
    table.add_column("detail")
    table.add_row("local", "ok" if local.health() else "down", local.store_hint())
    try:
        import modal  # noqa: F401

        from crowe_mycelium.backends.cloud import CloudModalBackend

        cloud = CloudModalBackend(app=settings.cloud_app, func=settings.cloud_func)
        cloud_status = "ok" if cloud.health() else "down"
        cloud_detail = f"modal app {settings.cloud_app} (paid always-on if min_containers=1)"
    except ImportError:
        cloud_status = "down"
        cloud_detail = "modal SDK not installed (pip install modal)"
    table.add_row("cloud", cloud_status, cloud_detail)
    console.print(table)


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="crowe-mycelium")
@click.option("--temperature", "-t", default=0.4, show_default=True, type=float)
@click.option("--local", "force_local", is_flag=True, help="Force the local Ollama backend.")
@click.option("--cloud", "force_cloud", is_flag=True, help="Force the Modal cloud backend.")
@click.option("--auto", "force_auto", is_flag=True, help="Cloud-first, local fallback (default).")
@click.pass_context
def main(ctx, temperature, force_local, force_cloud, force_auto) -> None:
    """Crowe Mycelium — cultivation intelligence on Gemma 4 Mycelium."""
    load_dotenv()
    ctx.ensure_object(dict)
    if sum([force_local, force_cloud, force_auto]) > 1:
        raise click.UsageError("--local, --cloud, and --auto are mutually exclusive.")
    ctx.obj["temperature"] = temperature
    ctx.obj["backend"] = (
        "local" if force_local else "cloud" if force_cloud else "auto" if force_auto else None
    )
    if ctx.invoked_subcommand is None:
        _chat_loop(ctx)


@main.command()
@click.pass_context
def chat(ctx) -> None:
    """Interactive chat session."""
    _chat_loop(ctx)


@main.command()
@click.argument("prompt", nargs=-1, required=True)
@click.pass_context
def run(ctx, prompt) -> None:
    """One-shot prompt. Streams to stdout (plain when piped)."""
    settings = _settings(ctx)
    backend = build_backend(settings)
    system = load_system_prompt()
    messages = _build_messages([], system, " ".join(prompt))
    renderer = PlainRenderer() if not sys.stdout.isatty() else RichRenderer()
    try:
        renderer.render_stream(backend.stream_chat(messages, settings.temperature))
    except Exception as e:
        renderer.error(str(e))
        sys.exit(1)


@main.command()
@click.pass_context
def info(ctx) -> None:
    """Model + backend status."""
    settings = _settings(ctx)
    _print_info(load_model_spec(), settings)
    branding.footer()


@main.command()
def models() -> None:
    """List registered models."""
    spec = load_model_spec()
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("name", style="bold")
    table.add_column("label")
    table.add_column("base")
    table.add_row(spec.name, spec.label, spec.base_model)
    console.print(table)
    branding.footer()


@main.command()
@click.pass_context
def doctor(ctx) -> None:
    """Diagnose local + cloud reachability."""
    _doctor_report(_settings(ctx))
    branding.footer()


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8014, show_default=True, type=int)
def serve(host, port) -> None:
    """Run an OpenAI-compatible /v1 gateway over the mycology model."""
    import uvicorn

    from crowe_mycelium.serve import build_app

    uvicorn.run(build_app(), host=host, port=port)


if __name__ == "__main__":
    main()
