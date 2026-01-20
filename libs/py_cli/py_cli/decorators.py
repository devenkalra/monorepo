# decorators.py

def async_command(func):
    """
    Decorator to mark a do_ function as requiring asynchronous execution.
    Attaches the attribute run_mode='async' to the function.
    """
    setattr(func, 'run_mode', 'async')
    return func

# You could also add a decorator for sync, but the absence of the attribute
# is typically used to mean 'sync' (the default mode).