import asyncio
import requests
from functools import wraps
from math import floor
from trame.widgets.html import Span
from trame.widgets.vuetify2 import (VTooltip, Template, VBtn, VIcon)
from typing import Callable, Optional


class Button():
    def __init__(
        self,
        *,
        tooltip: str = None,
        text: str = None,
        text_color: str = "black",
        icon: str = None,
        icon_color: str = "black",
        click: Optional[Callable] = None,
        size: int = 40,
        **kwargs,
    ) -> None:

        with VTooltip(
            tooltip,
            v_if=kwargs.get("v_if", True),
            right=text is None,
            bottom=text is not None,
            transition="slide-x-transition" if text is None else "slide-y-transition",
            disabled=tooltip is None,
        ):
            with Template(v_slot_activator="{ on, attrs }"):
                with VBtn(
                    text=text is None and icon is not None,
                    rounded=text is None,
                    height=None if text is not None else size,
                    width=None if text is not None else size,
                    min_height=None if text is not None else size,
                    min_width=None if text is not None else size,
                    click=click,
                    v_bind="attrs",
                    v_on="on",
                    **kwargs,
                ):
                    if text is not None:
                        Span(text, style=f"color:{text_color}")
                    if icon is not None:
                        VIcon(icon, size=floor(0.6 * size), color=icon_color)

def is_valid_url(url):
    """
    Checks if the given URL is valid and reachable.
    Returns:
        (True, None) if valid.
        (False, "Error message") if invalid.
    """
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return True, None
        return False, "Invalid URL"
    except (requests.exceptions.ConnectionError, requests.exceptions.RequestException):
        return False, "Unable to connect"
    except requests.exceptions.Timeout:
        return False, "Connection timed out"
    except requests.exceptions.MissingSchema:
        return False, "Invalid URL format"

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
