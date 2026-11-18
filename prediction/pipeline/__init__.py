"""Prediction pipeline and shared errors."""


class MagnetogramNotFoundError(RuntimeError):
    """No magnetogram meets the forecast slot's observation window."""
