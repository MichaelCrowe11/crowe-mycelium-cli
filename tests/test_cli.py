from click.testing import CliRunner

import crowe_mycelium.cli as climod
from crowe_mycelium.cli import main
from tests.conftest import FakeBackend


def test_run_uses_backend_and_prints_answer(monkeypatch):
    monkeypatch.setattr(
        climod, "build_backend", lambda settings: FakeBackend(chunks=["600-1200 ppm"])
    )
    monkeypatch.setattr(climod, "load_system_prompt", lambda: "SYS")
    result = CliRunner().invoke(main, ["run", "co2", "for", "oyster"])
    assert result.exit_code == 0
    assert "600-1200 ppm" in result.output


def test_backend_flag_selects_local(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        climod,
        "build_backend",
        lambda settings: seen.setdefault("backend", settings.backend) or FakeBackend(),
    )
    monkeypatch.setattr(climod, "load_system_prompt", lambda: "SYS")
    CliRunner().invoke(main, ["--local", "run", "hi"])
    assert seen["backend"] == "local"


def test_models_lists_the_model():
    result = CliRunner().invoke(main, ["models"])
    assert result.exit_code == 0
    assert "Gemma 4 Mycelium" in result.output
