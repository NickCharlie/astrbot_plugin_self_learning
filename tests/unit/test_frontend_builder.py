"""frontend_builder 单元测试：产物检测、工具探测、降级路径。

不触发真实 subprocess 构建，仅验证纯逻辑与降级行为。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.webui import frontend_builder


# ---------- dashboard_artifact_exists ----------

def test_dashboard_artifact_exists_true_for_plugin_root():
    """真实插件根目录已含构建产物。"""
    assert frontend_builder.dashboard_artifact_exists(str(PACKAGE_ROOT)) is True


def test_dashboard_artifact_exists_false_for_empty_dir(tmp_path):
    """空目录无产物。"""
    assert frontend_builder.dashboard_artifact_exists(str(tmp_path)) is False


def test_dashboard_artifact_exists_false_when_referenced_asset_missing(tmp_path):
    """只有 index.html 但引用资源缺失时不能视为产物完整。"""
    dashboard_dir = tmp_path / "web_res" / "static" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "index.html").write_text(
        '<script type="module" src="/static/dashboard/assets/index-missing.js"></script>',
        encoding="utf-8",
    )

    assert frontend_builder.dashboard_artifact_exists(str(tmp_path)) is False


# ---------- _tool_name ----------

def test_tool_name_recognizes_pnpm():
    assert frontend_builder._tool_name("/usr/local/bin/pnpm") == "pnpm"
    assert frontend_builder._tool_name(r"C:\nodejs\pnpm.CMD") == "pnpm"


def test_tool_name_recognizes_npm():
    assert frontend_builder._tool_name("/usr/local/bin/npm") == "npm"
    assert frontend_builder._tool_name(r"C:\nodejs\npm.cmd") == "npm"


# ---------- detect_build_tool ----------

def test_detect_build_tool_returns_none_without_node():
    with patch.object(frontend_builder.shutil, "which", return_value=None):
        assert frontend_builder.detect_build_tool() is None


def test_detect_build_tool_prefers_pnpm_over_npm():
    def fake_which(name):
        return {"node": "/n/node", "pnpm": "/n/pnpm", "npm": "/n/npm"}.get(name)

    with patch.object(frontend_builder.shutil, "which", side_effect=fake_which):
        assert frontend_builder.detect_build_tool() == "/n/pnpm"


def test_detect_build_tool_falls_back_to_npm():
    def fake_which(name):
        return {"node": "/n/node", "npm": "/n/npm"}.get(name)

    with patch.object(frontend_builder.shutil, "which", side_effect=fake_which):
        assert frontend_builder.detect_build_tool() == "/n/npm"


# ---------- ensure_dashboard_built ----------

@pytest.mark.asyncio
async def test_ensure_dashboard_built_skips_when_artifact_present():
    """产物已就绪则直接返回 True，不触发构建。"""
    with patch.object(frontend_builder, "dashboard_artifact_exists", return_value=True), \
         patch.object(frontend_builder, "_run_build_subprocess") as mock_run:
        result = await frontend_builder.ensure_dashboard_built("/anywhere")
        assert result is True
        mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_dashboard_built_degrades_when_no_tool():
    """产物缺失且无 Node 工具链时降级返回 False，不抛异常。"""
    with patch.object(frontend_builder, "dashboard_artifact_exists", return_value=False), \
         patch.object(frontend_builder, "detect_build_tool", return_value=None):
        result = await frontend_builder.ensure_dashboard_built("/anywhere")
        assert result is False


@pytest.mark.asyncio
async def test_ensure_dashboard_built_concurrency_guard(tmp_path):
    """并发调用时进程级标记阻止重复构建。"""
    frontend_builder._building = False
    call_count = {"n": 0}

    async def fake_run(root):
        call_count["n"] += 1
        # 模拟耗时构建：让出事件循环，使第二个协程能进入守卫检查
        await asyncio.sleep(0.05)
        return True, "ok"

    def exists_side_effect(root):
        # 始终返回 False，强制进入构建路径以触发并发守卫
        return False

    with patch.object(frontend_builder, "dashboard_artifact_exists", side_effect=exists_side_effect), \
         patch.object(frontend_builder, "_run_build_subprocess", side_effect=fake_run):
        r1, r2 = await asyncio.gather(
            frontend_builder.ensure_dashboard_built(str(tmp_path)),
            frontend_builder.ensure_dashboard_built(str(tmp_path)),
        )
        # fake_run 只应被执行一次；另一个调用被并发守卫拦截
        assert call_count["n"] == 1
        assert {r1, r2} == {True, False}
