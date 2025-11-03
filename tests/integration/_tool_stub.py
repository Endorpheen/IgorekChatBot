from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable
from unittest.mock import patch


def _tool_passthrough(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]] | Callable[..., Any]:
    """Return a decorator that keeps the original function intact.

    Supports both @tool usage with and without parentheses.
    """

    if args and callable(args[0]) and len(args) == 1 and not kwargs:
        return args[0]

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    return decorator


@contextmanager
def stub_langchain_tool() -> None:
    with patch("langchain.tools.tool", _tool_passthrough):
        yield
