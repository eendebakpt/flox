# The functions defined here were copied based on the source code
# defined in xarray


from typing import Any, Iterable

import dask.array
import numpy as np
import pandas as pd


def is_duck_array(value: Any) -> bool:
    """Checks if value is a duck array."""
    if isinstance(value, np.ndarray):
        return True
    return (
        hasattr(value, "ndim")
        and hasattr(value, "shape")
        and hasattr(value, "dtype")
        and hasattr(value, "__array_function__")
        and hasattr(value, "__array_ufunc__")
    )


def is_dask_collection(x):
    try:
        import dask

        return dask.is_dask_collection(x)

    except ImportError:
        return False


def is_duck_dask_array(x):
    return is_duck_array(x) and is_dask_collection(x)


class ReprObject:
    """Object that prints as the given value, for use with sentinel values."""

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def __repr__(self) -> str:
        return self._value

    def __eq__(self, other) -> bool:
        if isinstance(other, ReprObject):
            return self._value == other._value
        return False

    def __hash__(self) -> int:
        return hash((type(self), self._value))

    def __dask_tokenize__(self):
        from dask.base import normalize_token

        return normalize_token((type(self), self._value))


def is_scalar(value: Any, include_0d: bool = True) -> bool:
    """Whether to treat a value as a scalar.

    Any non-iterable, string, or 0-D array
    """
    NON_NUMPY_SUPPORTED_ARRAY_TYPES = (dask.array.Array, pd.Index)

    if include_0d:
        include_0d = getattr(value, "ndim", None) == 0
    return (
        include_0d
        or isinstance(value, (str, bytes))
        or not (
            isinstance(value, (Iterable,) + NON_NUMPY_SUPPORTED_ARRAY_TYPES)
            or hasattr(value, "__array_function__")
        )
    )
