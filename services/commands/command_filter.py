"""AstrBot 命令检测过滤器 — 区分命令消息与普通消息"""
import re
from typing import Any


class CommandFilter:
    """判断消息是否为 AstrBot 命令或本插件命令"""

    PLUGIN_COMMANDS = [
        "learning_status",
        "start_learning",
        "stop_learning",
        "force_learning",
        "affection_status",
        "set_mood",
    ]

    def is_astrbot_command(self, event: Any) -> bool:
        """判断用户输入是否为 AstrBot 命令（包括插件命令和其他命令）

        注意：唤醒词消息（is_at_or_wake_command）应该被收集用于学习，
        因为这些是最有价值的对话数据。只过滤明确的命令格式。
        """
        message_text = event.get_message_str()
        if not message_text:
            return False

        if self.is_plugin_command(message_text):
            return True

        command_prefixes = ["/", "!", "#", "."]
        stripped_text = message_text.strip()
        if stripped_text and stripped_text[0] in command_prefixes:
            if len(stripped_text) > 1 and stripped_text[1].isalpha():
                return True

        return False

    def is_plugin_command(self, message_text: str) -> bool:
        """检查消息是否为本插件的命令"""
        if not message_text:
            return False

        message_text = message_text.strip()

        commands_pattern = "|".join(re.escape(cmd) for cmd in self.PLUGIN_COMMANDS)
        pattern_with_prefix = rf"^.{{1}}({commands_pattern})(\s.*)?$"
        pattern_without_prefix = rf"^({commands_pattern})(\s.*)?$"

        return bool(
            re.match(pattern_with_prefix, message_text, re.IGNORECASE)
        ) or bool(
            re.match(pattern_without_prefix, message_text, re.IGNORECASE)
        )
