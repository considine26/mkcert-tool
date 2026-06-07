"""
validators.py - 交互式输入校验工具
"""

from rich.prompt import Prompt


def prompt_positive_int(
    message: str,
    default: str | int,
    *,
    min_value: int = 1,
    max_value: int | None = None,
) -> int:
    """循环提示用户输入正整数，可选上限。"""
    while True:
        value = Prompt.ask(message, default=str(default)).strip()
        try:
            number = int(value)
        except ValueError:
            print("请输入有效的整数。")
            continue

        if number < min_value:
            print(f"请输入不小于 {min_value} 的整数。")
            continue
        if max_value is not None and number > max_value:
            print(f"请输入不大于 {max_value} 的整数。")
            continue
        return number
