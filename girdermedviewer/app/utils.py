import asyncio
from functools import wraps
from math import floor

from trame.widgets.vuetify2 import (VTooltip, Template, VBtn, VIcon)
from typing import Callable, Optional


class Button():
    def __init__(
        self,
        *,
        tooltip: str,
        icon: str,
        icon_color: str = None,
        click: Optional[Callable] = None,
        size: int = 40,
        **kwargs,
    ) -> None:

        with VTooltip(
            tooltip,
            right=True,
            transition="slide-x-transition"
        ):
            with Template(v_slot_activator="{ on, attrs }"):
                with VBtn(
                    text=True,
                    rounded=0,
                    height=size,
                    width=size,
                    min_height=size,
                    min_width=size,
                    click=click,
                    v_bind="attrs",
                    v_on="on",
                    **kwargs,
                ):
                    VIcon(icon, size=floor(0.6 * size), color=icon_color)


def debounce(wait, disabled=False):
    """
    Debounce decorator to delay the execution of a function or method.
    If the function is called again before the wait time is over, the timer resets.

    :param wait: Time to wait (in seconds) before executing the function or method.
    :param disabled: debouncing can be disabled at declaration time
    """
    def decorator(func):
        _debounce_tasks = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Determine the key to store the debounce task:
            # For instance or class methods, use the instance/class as the key
            # For standalone functions, use the function itself as the key
            if len(args) > 0 and hasattr(args[0], "__dict__"):  # Likely a method
                key = (args[0], func)  # Use (instance, func) as the unique key
            else:  # Standalone function
                key = func

            # Cancel the existing task if it exists
            if key in _debounce_tasks:
                _debounce_tasks[key].cancel()

            # Define the delayed execution task
            async def delayed_execution():
                try:
                    await asyncio.sleep(wait)
                    func(*args, **kwargs)
                except asyncio.CancelledError:
                    pass  # Task was canceled
                except Exception as e:
                    print(e)

            # Create and store the new task
            _debounce_tasks[key] = asyncio.create_task(delayed_execution())

        return wrapper

    if disabled:
        return lambda func: func
    else:
        return decorator
