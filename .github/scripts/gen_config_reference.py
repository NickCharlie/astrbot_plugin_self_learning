"""由 _conf_schema.json 生成 docs/configuration.md 中的「完整配置参考」。

插件配置以 _conf_schema.json 为唯一事实源（AstrBot 插件配置页与两个 WebUI
设置页都由它渲染）。手写的配置表格必然随版本漂移，因此参考表由本脚本生成，
写在文档的标记区间内；测试 tests/unit/test_docs_config_reference.py 会以
--check 模式校验，schema 改了而文档没重新生成时 CI 直接失败。

用法：
    python .github/.github/scripts/gen_config_reference.py          # 重新生成并写回文档
    python .github/.github/scripts/gen_config_reference.py --check  # 只校验，不一致时退出码 1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "_conf_schema.json"
DOC_PATH = ROOT / "docs" / "configuration.md"
START = "<!-- CONFIG-REFERENCE:START 由 .github/scripts/gen_config_reference.py 生成，请勿手改 -->"
END = "<!-- CONFIG-REFERENCE:END -->"

TYPE_LABELS = {
    "bool": "布尔",
    "int": "整数",
    "float": "小数",
    "string": "文本",
    "text": "长文本",
    "list": "列表",
}


def _cell(text: str) -> str:
    """表格单元格安全化：竖线转义、换行转 <br>。"""
    return str(text).replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>").strip()


def _default(item: dict) -> str:
    if "default" not in item:
        return "—"
    value = item["default"]
    if item.get("_secret") and value:
        return "（已隐藏）"
    if value is None:
        return "`null`"
    if isinstance(value, str):
        return f"`{value}`" if value else '`""`'
    return f"`{json.dumps(value, ensure_ascii=False)}`"


def _description(item: dict) -> str:
    title = str(item.get("description") or "").strip()
    hint = str(item.get("hint") or "").strip()
    text = f"**{_cell(title)}**" if title else ""
    if hint and hint != title:
        text += ("：" if text else "") + _cell(hint)
    options = item.get("options")
    if options:
        labels = item.get("labels") or []
        rendered = []
        for index, option in enumerate(options):
            shown = option if option != "" else '""'
            label = labels[index] if index < len(labels) and labels[index] not in ("", option) else ""
            rendered.append(f"`{shown}`" + (f"（{_cell(label)}）" if label else ""))
        text += "<br>可选：" + " / ".join(rendered)
    flags = []
    if item.get("_readonly"):
        flags.append("只读")
    if item.get("_secret"):
        flags.append("敏感信息，界面中隐藏显示")
    if flags:
        text += "<br>（" + "，".join(flags) + "）"
    return text


def render(schema: dict) -> str:
    lines = [START, "", "## 完整配置参考", ""]
    lines.append(
        f"以下 {sum(len(g.get('items', {})) for g in schema.values())} 个配置项按 "
        f"{len(schema)} 个配置组列出，内容与 AstrBot 插件配置页一致。"
    )
    lines.append("")
    for group_key, group in schema.items():
        items = group.get("items", {})
        if not items:
            continue
        lines.append(f"### {group.get('description') or group_key}")
        lines.append("")
        lines.append(f"配置组：`{group_key}`")
        group_hint = str(group.get("hint") or "").strip()
        if group_hint:
            lines.append("")
            lines.append(f"> {_cell(group_hint)}")
        lines.append("")
        lines.append("| 字段 | 类型 | 默认值 | 说明 |")
        lines.append("| --- | --- | --- | --- |")
        for key, item in items.items():
            type_label = TYPE_LABELS.get(item.get("type"), item.get("type") or "—")
            lines.append(f"| `{key}` | {type_label} | {_default(item)} | {_description(item)} |")
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def updated_document(doc: str, block: str) -> str:
    if START in doc and END in doc:
        head = doc.split(START, 1)[0]
        tail = doc.split(END, 1)[1]
        return head + block + tail
    return doc.rstrip("\n") + "\n\n" + block + "\n"


def main(argv: list[str]) -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = DOC_PATH.read_text(encoding="utf-8")
    expected = updated_document(doc, render(schema))
    if "--check" in argv:
        if expected != doc:
            print("docs/configuration.md 的配置参考与 _conf_schema.json 不一致，请运行 python .github/.github/scripts/gen_config_reference.py")
            return 1
        print("docs/configuration.md 配置参考与 schema 一致")
        return 0
    DOC_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print("已更新 docs/configuration.md 配置参考")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
