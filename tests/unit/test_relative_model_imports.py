"""回归测试：services/webui 子包内 models 相对导入的层级必须正确。

4.4.0 事故：``services/learning/forgetting_manager.py`` 与
``services/state/emotion_learning_gate.py`` 误用 ``from ..models.orm``
（两个点解析到 ``services.models``），fallback 的绝对导入
``from models.orm`` 又恰好在部分环境可解析，测试被掩盖；真实 AstrBot
以包路径加载插件时两者都失败，插件直接加载崩溃（No module named 'models'）。
"""

import importlib
import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

PACKAGE_NAME = "self_learning_EterU"


def _load_with_absolute_models_blocked(module_name: str):
    """屏蔽绝对导入 ``import models`` 后按包路径加载目标模块。

    相对导入层级写错时，try 分支失败、fallback 绝对导入也被屏蔽，
    模块加载即抛 ModuleNotFoundError —— 与真实 AstrBot 部署一致。
    """
    saved = sys.modules.get("models", ...)
    sys.modules["models"] = None  # None 使任何 `import models` 立即 ImportError
    # 目标模块若已被（错误的）先前导入缓存，先清掉
    for name in list(sys.modules):
        if name == module_name or name.startswith(module_name + "."):
            del sys.modules[name]
    try:
        return importlib.import_module(module_name)
    finally:
        if saved is ...:
            sys.modules.pop("models", None)
        else:
            sys.modules["models"] = saved


def test_forgetting_manager_imports_via_package_relative_path():
    module = _load_with_absolute_models_blocked(
        f"{PACKAGE_NAME}.services.learning.forgetting_manager"
    )
    # ORM 必须来自插件包内的 models，而不是环境里恰好存在的顶层 models
    assert module.ExpressionPattern.__module__.startswith(f"{PACKAGE_NAME}.models")


def test_emotion_learning_gate_imports_via_package_relative_path():
    module = _load_with_absolute_models_blocked(
        f"{PACKAGE_NAME}.services.state.emotion_learning_gate"
    )
    assert module.LearningGateDailyStat.__module__.startswith(f"{PACKAGE_NAME}.models")


def test_all_relative_model_imports_match_directory_depth():
    """结构化扫描：``from <N 个点>models`` 的点数必须等于目录深度 + 1。

    Python 相对导入语义：K 个点 = 从当前包上跳 K-1 级。文件位于
    ``services/learning/x.py``（目录深度 2）时，上跳 2 级到插件根需要
    3 个点。全仓库既有文件均符合该规则。
    """
    pattern = re.compile(r"^\s*from (\.+)models\b", re.MULTILINE)
    offenders = []
    for base in (PACKAGE_ROOT / "services", PACKAGE_ROOT / "webui", PACKAGE_ROOT / "core"):
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in pattern.finditer(text):
                dots = len(match.group(1))
                depth = len(path.relative_to(PACKAGE_ROOT).parts) - 1
                if dots != depth + 1:
                    offenders.append(
                        f"{path.relative_to(PACKAGE_ROOT)}: {match.group(0).strip()}"
                        f"（{dots} 个点，应为 {depth + 1}）"
                    )
    assert not offenders, "models 相对导入层级错误:\n" + "\n".join(offenders)
