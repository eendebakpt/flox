import numpy as np
import pandas as pd
from asv_runner.benchmarks.mark import parameterize, skip_for_params

import flox
import flox.aggregations

N = 3000
funcs = ["sum", "nansum", "mean", "nanmean", "max", "nanmax", "count"]
engines = [None, "flox", "numpy", "numbagg"]
expected_groups = {
    "None": None,
    "bins": pd.IntervalIndex.from_breaks([1, 2, 4]),
}
expected_names = tuple(expected_groups)

NUMBAGG_FUNCS = ["nansum", "nanmean", "nanmax", "count", "all"]
numbagg_skip = []
for name in expected_names:
    numbagg_skip.extend(
        list((func, name, "numbagg") for func in funcs if func not in NUMBAGG_FUNCS)
    )


def setup_jit():
    # pre-compile jitted funcs
    labels = np.ones((N), dtype=int)
    array1 = np.ones((N), dtype=float)
    array2 = np.ones((N, N), dtype=float)

    if "numba" in engines:
        for func in funcs:
            method = getattr(flox.aggregate_npg, func)
            method(labels, array1, engine="numba")
    if "numbagg" in engines:
        for func in set(NUMBAGG_FUNCS) & set(funcs):
            flox.groupby_reduce(array1, labels, func=func, engine="numbagg")
            flox.groupby_reduce(array2, labels, func=func, engine="numbagg")


class ChunkReduce:
    """Time the core reduction function."""

    min_run_count = 5
    warmup_time = 0.5

    def setup(self, *args, **kwargs):
        raise NotImplementedError

    @skip_for_params(numbagg_skip)
    @parameterize({"func": funcs, "expected_name": expected_names, "engine": engines})
    def time_reduce(self, func, expected_name, engine):
        flox.groupby_reduce(
            self.array,
            self.labels,
            func=func,
            engine=engine,
            axis=self.axis,
            expected_groups=expected_groups[expected_name],
        )

    @skip_for_params(numbagg_skip)
    @parameterize({"func": funcs, "expected_name": expected_names, "engine": engines})
    def peakmem_reduce(self, func, expected_name, engine):
        flox.groupby_reduce(
            self.array,
            self.labels,
            func=func,
            engine=engine,
            axis=self.axis,
            expected_groups=expected_groups[expected_name],
        )


class ChunkReduce1D(ChunkReduce):
    def setup(self, *args, **kwargs):
        self.array = np.ones((N,))
        self.labels = np.repeat(np.arange(5), repeats=N // 5)
        self.axis = -1
        if "numbagg" in args:
            setup_jit()

    @parameterize(
        {
            "func": ["nansum", "nanmean", "nanmax", "count"],
            "engine": [e for e in engines if e is not None],
        }
    )
    def time_reduce_bare(self, func, engine):
        # TODO: migrate to the other test cases, but we'll have to setup labels
        # appropriately ;(
        flox.aggregations.generic_aggregate(
            self.labels,
            self.array,
            axis=self.axis,
            func=func,
            engine=engine,
            fill_value=0,
        )


class ChunkReduce2D(ChunkReduce):
    def setup(self, *args, **kwargs):
        self.array = np.ones((N, N))
        self.labels = np.repeat(np.arange(N // 5), repeats=5)
        self.axis = -1
        setup_jit()


class ChunkReduce2DAllAxes(ChunkReduce):
    def setup(self, *args, **kwargs):
        self.array = np.ones((N, N))
        self.labels = np.repeat(np.arange(N // 5), repeats=5)[np.newaxis, :]
        self.axis = None
        setup_jit()


# class ChunkReduce2DUnsorted(ChunkReduce):
#     def setup(self, *args, **kwargs):
#         self.array = np.ones((N, N))
#         self.labels = np.random.permutation(np.repeat(np.arange(N // 5), repeats=5))
#         self.axis = -1
#         setup_jit()

# class ChunkReduce1DUnsorted(ChunkReduce):
#     def setup(self, *args, **kwargs):
#         self.array = np.ones((N,))
#         self.labels = np.random.permutation(np.repeat(np.arange(5), repeats=N // 5))
#         self.axis = -1
#         setup_jit()


# class ChunkReduce2DAllAxesUnsorted(ChunkReduce):
#     def setup(self, *args, **kwargs):
#         self.array = np.ones((N, N))
#         self.labels = np.random.permutation(np.repeat(np.arange(N // 5), repeats=5))
#         self.axis = None
#         setup_jit()
