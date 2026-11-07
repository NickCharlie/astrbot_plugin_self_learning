"""Optional Guardrails failures keep local structured validation available."""
import builtins
import importlib.util
from pathlib import Path

import pytest
from pydantic import BaseModel


@pytest.mark.parametrize("error_type", [ImportError, AttributeError])
def test_optional_guardrails_import_uses_pydantic_fallback(monkeypatch, error_type):
    original_import = builtins.__import__

    def import_with_unavailable_guardrails(name, *args, **kwargs):
        if name == "guardrails":
            raise error_type("optional guardrails cannot import openai.error")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_with_unavailable_guardrails)
    module_path = Path(__file__).resolve().parents[2] / "utils/guardrails_manager.py"
    spec = importlib.util.spec_from_file_location("utils._guardrails_optional_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class StructuredResult(BaseModel):
        count: int

    guard = module.Guard.for_pydantic(StructuredResult)
    valid = guard.parse('{"count": 3}')
    assert valid.validation_passed is True
    assert valid.validated_output.count == 3
    assert guard.parse('{"count": "invalid"}').validation_passed is False
    assert guard.parse("not JSON").validation_passed is False


def test_successful_optional_guardrails_import_keeps_original_class(monkeypatch):
    original_import = builtins.__import__

    class AvailableGuard:
        pass

    class AvailablePackage:
        Guard = AvailableGuard

    def import_with_available_guardrails(name, *args, **kwargs):
        if name == "guardrails":
            return AvailablePackage
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_with_available_guardrails)
    module_path = Path(__file__).resolve().parents[2] / "utils/guardrails_manager.py"
    spec = importlib.util.spec_from_file_location("utils._guardrails_available_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.Guard is AvailableGuard
