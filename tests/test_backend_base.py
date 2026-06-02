import pytest

from crowe_mycelium.backends.base import Backend
from tests.conftest import FakeBackend


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        Backend()  # cannot instantiate the ABC directly


def test_fake_backend_satisfies_interface():
    b = FakeBackend(name="x", chunks=["a", "b"])
    assert b.health() is True
    assert list(b.stream_chat([{"role": "user", "content": "hi"}])) == ["a", "b"]
    assert b.name == "x"
    assert b.label == "x · test"
