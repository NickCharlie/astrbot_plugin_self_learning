"""AstrBot provider registry inspection helpers.

These helpers intentionally inspect provider lists before falling back to
``context.get_provider_by_id``. During AstrBot cold start the registry can be
temporarily empty; probing by ID in that window makes the framework emit
"provider not found" warnings for an otherwise valid configuration.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple, Type, TypeVar


T = TypeVar("T")


def normalize_provider_id(value: Any) -> Optional[str]:
    """Return a stripped provider ID, or ``None`` for empty values."""
    if value is None:
        return None
    provider_id = str(value).strip()
    return provider_id or None


def collect_framework_providers(
    context: Any,
    provider_cls: Type[T],
    *,
    context_getter_name: Optional[str] = None,
    manager_list_name: Optional[str] = None,
) -> Tuple[List[T], bool, List[str]]:
    """Collect known framework providers for a type.

    Returns ``(providers, inspected, errors)``. ``inspected`` is true when the
    context exposed at least one list-like registry source. If it is true and
    ``providers`` is empty, callers should treat the framework registry as not
    ready and avoid noisy ID lookups.
    """
    providers: List[T] = []
    inspected = False
    errors: List[str] = []

    if context_getter_name:
        getter = _safe_getattr(context, context_getter_name)
        if callable(getter):
            inspected = True
            try:
                _extend_provider_list(providers, getter(), provider_cls)
            except Exception as exc:
                errors.append(f"{context_getter_name}: {exc}")

    provider_manager = _safe_getattr(context, "provider_manager")
    if provider_manager is not None:
        if manager_list_name:
            manager_list = _safe_getattr(provider_manager, manager_list_name)
            if manager_list is not None:
                inspected = True
                try:
                    _extend_provider_list(providers, manager_list, provider_cls)
                except Exception as exc:
                    errors.append(f"provider_manager.{manager_list_name}: {exc}")

        inst_map = _safe_getattr(provider_manager, "inst_map")
        if inst_map is not None:
            inspected = True
            try:
                values = inst_map.values() if isinstance(inst_map, dict) else inst_map
                _extend_provider_list(providers, values, provider_cls)
            except Exception as exc:
                errors.append("provider_manager.inst_map: " + str(exc))

    return _dedupe_providers(providers), inspected, errors


def framework_registry_has_any_provider(context: Any) -> Tuple[bool, bool, List[str]]:
    """Return whether any framework provider is visible in known registries."""
    inspected = False
    errors: List[str] = []

    for getter_name in (
        "get_all_providers",
        "get_all_embedding_providers",
        "get_all_rerank_providers",
    ):
        getter = _safe_getattr(context, getter_name)
        if not callable(getter):
            continue
        inspected = True
        try:
            if _as_list(getter()):
                return True, inspected, errors
        except Exception as exc:
            errors.append(f"{getter_name}: {exc}")

    provider_manager = _safe_getattr(context, "provider_manager")
    if provider_manager is not None:
        for attr_name in (
            "provider_insts",
            "embedding_provider_insts",
            "rerank_provider_insts",
            "inst_map",
        ):
            value = _safe_getattr(provider_manager, attr_name)
            if value is None:
                continue
            inspected = True
            try:
                if _as_list(value):
                    return True, inspected, errors
            except Exception as exc:
                errors.append(f"provider_manager.{attr_name}: {exc}")

    return False, inspected, errors


def find_provider_by_id(providers: List[T], provider_id: str) -> Optional[T]:
    """Find a provider in a pre-inspected registry list by metadata ID."""
    for provider in providers:
        try:
            meta = provider.meta()  # type: ignore[attr-defined]
        except Exception:
            continue
        if getattr(meta, "id", None) == provider_id:
            return provider
    return None


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Read attributes without letting unconfigured Mock children look real."""
    if obj is None:
        return default

    try:
        attrs = vars(obj)
    except TypeError:
        attrs = {}

    if name in attrs:
        return attrs[name]

    if type(obj).__module__.startswith("unittest.mock"):
        return default

    try:
        return getattr(obj, name)
    except Exception:
        return default


def _extend_provider_list(
    providers: List[T],
    raw_value: Any,
    provider_cls: Type[T],
) -> None:
    for candidate in _as_list(raw_value):
        if isinstance(candidate, provider_cls):
            providers.append(candidate)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _dedupe_providers(providers: List[T]) -> List[T]:
    deduped: List[T] = []
    seen = set()
    for provider in providers:
        identity = id(provider)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(provider)
    return deduped
