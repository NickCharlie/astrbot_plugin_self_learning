"""Regression coverage for AstrBot plugin metadata."""

import ast
import json
from pathlib import Path

import yaml


PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def test_metadata_uses_astrbot_supported_compatibility_fields():
    metadata = yaml.safe_load((PLUGIN_ROOT / "metadata.yaml").read_text(encoding="utf-8"))

    assert metadata["astrbot_version"] == ">=4.11.4"
    assert metadata["support_platforms"] == [
        "aiocqhttp",
        "qq_official",
        "telegram",
    ]
    assert "compatibility" not in metadata
    assert "platforms" not in metadata


def test_release_versions_are_synchronized():
    metadata = yaml.safe_load((PLUGIN_ROOT / "metadata.yaml").read_text(encoding="utf-8"))
    package = json.loads((PLUGIN_ROOT / "web_src" / "package.json").read_text(encoding="utf-8"))
    init_tree = ast.parse((PLUGIN_ROOT / "__init__.py").read_text(encoding="utf-8"))
    runtime_version = next(
        node.value.value
        for node in init_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )

    assert metadata["version"] == runtime_version == package["version"]
