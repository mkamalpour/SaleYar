"""Lazy UI entry points: terminal and dashboard serving do not import Gradio."""

def run_developer(*args, **kwargs):
    from .developer import run
    return run(*args, **kwargs)

def run_owner(*args, **kwargs):
    from .owner import run
    return run(*args, **kwargs)

def run_terminal(*args, **kwargs):
    from .terminal import run_terminal as run
    return run(*args, **kwargs)

__all__ = ["run_developer", "run_owner", "run_terminal"]
