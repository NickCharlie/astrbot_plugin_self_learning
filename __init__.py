# AstrBot 自学习插件
__version__ = "Next-2.0.5"

# Ensure parent namespace packages ("data", "data.plugins") are
# durably registered in sys.modules.  AstrBot loads plugins via
# __import__("data.plugins.<name>.main"), which creates implicit
# namespace packages.  These can be invalidated when pip_installer
# manipulates sys.path / sys.modules during dependency recovery,
# causing deferred relative imports (from ...X import Y) to fail
# with "No module named 'data.plugins.<name>'".
import sys as _sys
import types as _types

_pkg_name = __name__  # e.g. "data.plugins.astrbot_plugin_self_learning"
_parts = _pkg_name.split(".")
for _i in range(1, len(_parts)):
    _ns = ".".join(_parts[:_i])
    if _ns not in _sys.modules:
        _mod = _types.ModuleType(_ns)
        _mod.__path__ = []
        _mod.__package__ = _ns
        _sys.modules[_ns] = _mod
