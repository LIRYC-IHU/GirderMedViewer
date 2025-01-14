import asyncio
from functools import wraps


def debounce(wait):
    """
    Debounce decorator to delay the execution of a function.
    If the function is called again before the wait time is over, the timer resets.
    
    :param wait: Time to wait (in seconds) before executing the function.
    """
    def decorator(func):
        func._debounce_task = None

        @wraps(func)
        def wrapper(*args, **kwargs):
            if func._debounce_task:
                func._debounce_task.cancel()
            func._debounce_task = asyncio.create_task(delayed_execution(func, wait, *args, **kwargs))

        async def delayed_execution(func, wait, *args, **kwargs):
            try:
                await asyncio.sleep(wait)
                await func(*args, **kwargs)
            except asyncio.CancelledError:
                pass  # Task was canceled

        return wrapper

    return decorator
