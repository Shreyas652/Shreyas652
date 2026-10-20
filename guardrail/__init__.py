"""Deterministic prompt-injection guard used by the profile challenge."""

from .engine import Assessment, assess

__all__ = ["Assessment", "assess"]
