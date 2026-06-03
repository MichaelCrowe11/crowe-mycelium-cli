"""Deep mode: a web-aware ensemble. Sample the model N times (temperature-diverse),
optionally grounded in web search, then a judge pass reconciles the candidates into
one best answer with an agreement/confidence signal.

Composes 1.5b (search/grounding) + 1.5a (streaming renderer). cli._build_messages
is passed in so this module never imports cli.
"""

from __future__ import annotations

import os

from crowe_mycelium.branding import console
from crowe_mycelium.grounding import format_grounding, needs_live_info, sources_text
from crowe_mycelium.search import build_searcher


def deep_samples() -> int:
    """How many candidate answers to draw (default 3, floored at 2)."""
    raw = os.environ.get("CROWE_MYCELIUM_DEEP_SAMPLES", "3")
    try:
        return max(2, int(raw))
    except ValueError:
        return 3


def deep_temperature() -> float:
    """Sampling temperature for the candidates (default 0.8 for diversity)."""
    raw = os.environ.get("CROWE_MYCELIUM_DEEP_TEMPERATURE", "0.8")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.8


def collect_sample(backend, messages, temperature) -> str:
    """Consume one full completion from the backend stream into a string."""
    return "".join(backend.stream_chat(messages, temperature))


def build_judge_messages(system: str, query: str, candidates: list[str]) -> list[dict]:
    """The reconciliation prompt: original question + numbered candidates + a
    directive to merge them and end with an agreement line."""
    n = len(candidates)
    numbered = "\n\n".join(f"[Answer {i}]\n{c}" for i, c in enumerate(candidates, 1))
    user = (
        f"Question: {query}\n\n"
        f"{n} independent expert answers were drafted:\n\n{numbered}\n\n"
        f"Reconcile them into ONE best answer. Where they agree, state it confidently; "
        f"where they diverge, choose the most evidence-grounded option and flag the "
        f"uncertainty. End with one line: 'agreement: <k>/{n} aligned' "
        f"(append ' — diverged on <topic>' if they differ)."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_deep(
    query, backend, system, history, settings, renderer, build_messages, *, force_web=False
):
    """Ensemble: optionally ground, sample N times, judge/reconcile, render.

    `build_messages` is cli._build_messages (passed to avoid importing cli)."""
    results = []
    if force_web or needs_live_info(query):
        try:
            results = build_searcher(settings).search(query)
        except NotImplementedError as e:
            renderer.notice(str(e))
            results = []
    user_turn = format_grounding(query, results) if results else query

    n = deep_samples()
    temp = deep_temperature()
    candidates: list[str] = []
    for i in range(n):
        messages = build_messages(history, system, user_turn)
        try:
            sample = renderer.deliberate(
                f"deliberating · sample {i + 1}/{n}",
                lambda m=messages: collect_sample(backend, m, temp),
            )
        except Exception:
            sample = ""  # a failed sample is skipped; reconcile over the rest
        if sample.strip():
            candidates.append(sample)

    if not candidates:
        renderer.error("deep mode: no answers produced.")
        return

    judge_messages = build_judge_messages(system, query, candidates)
    try:
        reply = renderer.render_stream(backend.stream_chat(judge_messages, 0.3))
    except Exception as e:
        renderer.error(str(e))
        return

    if results:
        console.print(f"[grey50]{sources_text(results)}[/]")
    history.append(("user", query))
    history.append(("assistant", reply))
