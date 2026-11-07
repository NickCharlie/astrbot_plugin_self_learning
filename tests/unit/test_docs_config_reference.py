"""回归测试：文档与事实源保持一致。

- docs/configuration.md 的「完整配置参考」由 scripts/gen_config_reference.py
  从 _conf_schema.json 生成；schema 改动而文档未重新生成时此测试失败。
- docs/README.md 声明的元数据版本必须与 metadata.yaml 一致。
"""

import re
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PACKAGE_ROOT / "scripts" / "gen_config_reference.py"
README_DOCS = PACKAGE_ROOT / "docs" / "README.md"
METADATA = PACKAGE_ROOT / "metadata.yaml"


def test_config_reference_matches_schema():
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=PACKAGE_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_docs_index_version_matches_metadata():
    version = re.search(r'^version: "([^"]+)"', METADATA.read_text(encoding="utf-8"), re.M).group(1)
    docs = README_DOCS.read_text(encoding="utf-8")
    assert f"当前元数据版本: `{version}`" in docs, (
        f"docs/README.md 的元数据版本与 metadata.yaml（{version}）不一致"
    )
