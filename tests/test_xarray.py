import numpy as np
import pandas as pd
import pytest

# isort: off
xr = pytest.importorskip("xarray")
# isort: on

from flox.xarray import rechunk_for_blockwise, xarray_reduce

from . import assert_equal, has_dask, raise_if_dask_computes, requires_dask

if has_dask:
    import dask

    dask.config.set(scheduler="sync")

try:
    # test against legacy xarray implementation
    xr.set_options(use_flox=False)
except ValueError:
    pass


tolerance64 = {"rtol": 1e-15, "atol": 1e-18}
np.random.seed(123)


@pytest.mark.parametrize("reindex", [None, False, True])
@pytest.mark.parametrize("min_count", [None, 1, 3])
@pytest.mark.parametrize("add_nan", [True, False])
@pytest.mark.parametrize("skipna", [True, False])
def test_xarray_reduce(skipna, add_nan, min_count, engine, reindex):
    if skipna is False and min_count is not None:
        pytest.skip()

    arr = np.ones((4, 12))

    if add_nan:
        arr[1, ...] = np.nan
        arr[[0, 2], [3, 4]] = np.nan

    labels = np.array(["a", "a", "c", "c", "c", "b", "b", "c", "c", "b", "b", "f"])
    labels = np.array(labels)
    labels2 = np.array([1, 2, 2, 1])

    da = xr.DataArray(
        arr, dims=("x", "y"), coords={"labels2": ("x", labels2), "labels": ("y", labels)}
    ).expand_dims(z=4)

    expected = da.groupby("labels").sum(skipna=skipna, min_count=min_count)
    actual = xarray_reduce(
        da, "labels", func="sum", skipna=skipna, min_count=min_count, engine=engine, reindex=reindex
    )
    assert_equal(expected, actual)

    da["labels2"] = da.labels2.astype(float)
    da["labels2"][0] = np.nan
    expected = da.groupby("labels2").sum(skipna=skipna, min_count=min_count)
    actual = xarray_reduce(
        da,
        "labels2",
        func="sum",
        skipna=skipna,
        min_count=min_count,
        engine=engine,
        reindex=reindex,
    )
    assert_equal(expected, actual)

    # test dimension ordering
    # actual = xarray_reduce(
    #    da.transpose("y", ...), "labels", func="sum", skipna=skipna, min_count=min_count
    # )
    # assert_equal(expected, actual)


# TODO: sort
@pytest.mark.parametrize("pass_expected_groups", [True, False])
@pytest.mark.parametrize("chunk", (pytest.param(True, marks=requires_dask), False))
def test_xarray_reduce_multiple_groupers(pass_expected_groups, chunk, engine):
    if chunk and pass_expected_groups is False:
        pytest.skip()

    arr = np.ones((4, 12))
    labels = np.array(["a", "a", "c", "c", "c", "b", "b", "c", "c", "b", "b", "f"])
    labels2 = np.array([1, 2, 2, 1])

    da = xr.DataArray(
        arr, dims=("x", "y"), coords={"labels2": ("x", labels2), "labels": ("y", labels)}
    ).expand_dims(z=4)

    if chunk:
        da = da.chunk({"x": 2, "z": 1})

    expected = xr.DataArray(
        [[4, 4], [8, 8], [10, 10], [2, 2]],
        dims=("labels", "labels2"),
        coords={"labels": ["a", "b", "c", "f"], "labels2": [1, 2]},
    ).expand_dims(z=4)

    kwargs = dict(func="count", engine=engine)
    if pass_expected_groups:
        kwargs["expected_groups"] = (expected.labels.data, expected.labels2.data)

    with raise_if_dask_computes():
        actual = xarray_reduce(da, da.labels, da.labels2, **kwargs)
    xr.testing.assert_identical(expected, actual)

    with raise_if_dask_computes():
        actual = xarray_reduce(da, "labels", da.labels2, **kwargs)
    xr.testing.assert_identical(expected, actual)

    with raise_if_dask_computes():
        actual = xarray_reduce(da, "labels", "labels2", **kwargs)
    xr.testing.assert_identical(expected, actual)

    if pass_expected_groups:
        kwargs["expected_groups"] = (expected.labels2.data, expected.labels.data)
    with raise_if_dask_computes():
        actual = xarray_reduce(da, "labels2", "labels", **kwargs)
    xr.testing.assert_identical(expected.transpose("z", "labels2", "labels"), actual)


@pytest.mark.parametrize("pass_expected_groups", [True, False])
@pytest.mark.parametrize("chunk", (pytest.param(True, marks=requires_dask), False))
def test_xarray_reduce_multiple_groupers_2(pass_expected_groups, chunk, engine):
    if chunk and pass_expected_groups is False:
        pytest.skip()

    arr = np.ones((2, 12))
    labels = np.array(["a", "a", "c", "c", "c", "b", "b", "c", "c", "b", "b", "f"])

    da = xr.DataArray(
        arr, dims=("x", "y"), coords={"labels2": ("y", labels), "labels": ("y", labels)}
    ).expand_dims(z=4)

    if chunk:
        da = da.chunk({"x": 2, "z": 1})

    expected = xr.DataArray(
        [[2, 0, 0, 0], [0, 4, 0, 0], [0, 0, 5, 0], [0, 0, 0, 1]],
        dims=("labels", "labels2"),
        coords={
            "labels": ["a", "b", "c", "f"],
            "labels2": ["a", "b", "c", "f"],
        },
    ).expand_dims(z=4, x=2)

    kwargs = dict(func="count", engine=engine)
    if pass_expected_groups:
        kwargs["expected_groups"] = (expected.labels.data, expected.labels.data)

    with raise_if_dask_computes():
        actual = xarray_reduce(da, "labels", "labels2", **kwargs)
    xr.testing.assert_identical(expected, actual)

    with pytest.raises(NotImplementedError):
        xarray_reduce(da, "labels", "labels2", dim=..., **kwargs)


@requires_dask
@pytest.mark.parametrize(
    "expected_groups",
    (None, (None, None), [[1, 2], [1, 2]]),
)
def test_validate_expected_groups(expected_groups):
    da = xr.DataArray(
        [1.0, 2.0], dims="x", coords={"labels": ("x", [1, 2]), "labels2": ("x", [1, 2])}
    )
    with pytest.raises(ValueError):
        xarray_reduce(
            da.chunk({"x": 1}),
            "labels",
            "labels2",
            func="count",
            expected_groups=expected_groups,
        )


@requires_dask
def test_xarray_reduce_single_grouper(engine):
    # DataArray
    ds = xr.tutorial.open_dataset("rasm", chunks={"time": 9})
    actual = xarray_reduce(ds.Tair, ds.time.dt.month, func="mean", engine=engine)
    expected = ds.Tair.groupby("time.month").mean()
    xr.testing.assert_allclose(actual, expected)

    # Ellipsis reduction
    actual = xarray_reduce(ds.Tair, ds.time.dt.month, func="mean", dim=..., engine=engine)
    expected = ds.Tair.groupby("time.month").mean(...)
    xr.testing.assert_allclose(actual, expected)

    # Dataset
    expected = ds.groupby("time.month").mean()
    actual = xarray_reduce(ds, ds.time.dt.month, func="mean", engine=engine)
    xr.testing.assert_allclose(actual, expected)

    # reduce along other dimensions
    expected = ds.groupby("time.month").mean(("x", "y"))
    actual = xarray_reduce(ds, ds.time.dt.month, dim=["x", "y"], func="mean", engine=engine)
    xr.testing.assert_allclose(actual, expected)

    # add data var with missing grouper dim
    ds["foo"] = ("bar", [1, 2, 3])
    expected = ds.groupby("time.month").mean()
    actual = xarray_reduce(ds, ds.time.dt.month, func="mean", engine=engine)
    xr.testing.assert_allclose(actual, expected)
    del ds["foo"]

    # non-dim coord with missing grouper dim
    ds.coords["foo"] = ("bar", [1, 2, 3])
    expected = ds.groupby("time.month").mean()
    actual = xarray_reduce(ds, ds.time.dt.month, func="mean", engine=engine)
    xr.testing.assert_allclose(actual, expected)
    del ds["foo"]

    # unindexed dim
    by = ds.time.dt.month.drop_vars("time")
    ds = ds.drop_vars("time")
    expected = ds.groupby(by).mean()
    actual = xarray_reduce(ds, by, func="mean")
    xr.testing.assert_allclose(actual, expected)


def test_xarray_reduce_errors():
    da = xr.DataArray(np.ones((12,)), dims="x")
    by = xr.DataArray(np.ones((12,)), dims="x")

    with pytest.raises(ValueError, match="group by unnamed"):
        xarray_reduce(da, by, func="mean")

    by.name = "by"
    with pytest.raises(ValueError, match="Cannot reduce over"):
        xarray_reduce(da, by, func="mean", dim="foo")

    if has_dask:
        with pytest.raises(ValueError, match="provide expected_groups"):
            xarray_reduce(da, by.chunk(), func="mean")


@requires_dask
@pytest.mark.parametrize(
    "inchunks, expected",
    [
        [(1,) * 10, (3, 2, 2, 3)],
        [(2,) * 5, (3, 2, 2, 3)],
        [(3, 3, 3, 1), (3, 2, 5)],
        [(3, 1, 1, 2, 1, 1, 1), (3, 2, 2, 3)],
        [(3, 2, 2, 3), (3, 2, 2, 3)],
        [(4, 4, 2), (3, 4, 3)],
        [(5, 5), (5, 5)],
        [(6, 4), (5, 5)],
        [(7, 3), (7, 3)],
        [(8, 2), (7, 3)],
        [(9, 1), (10,)],
        [(10,), (10,)],
    ],
)
def test_rechunk_for_blockwise(inchunks, expected):
    labels = np.array([1, 1, 1, 2, 2, 3, 3, 5, 5, 5])

    da = xr.DataArray(dask.array.ones((10,), chunks=inchunks), dims="x", name="foo")
    rechunked = rechunk_for_blockwise(da, "x", xr.DataArray(labels, dims="x"))
    assert rechunked.chunks == (expected,)

    da = xr.DataArray(dask.array.ones((5, 10), chunks=(-1, inchunks)), dims=("y", "x"), name="foo")
    rechunked = rechunk_for_blockwise(da, "x", xr.DataArray(labels, dims="x"))
    assert rechunked.chunks == ((5,), expected)
    ds = da.to_dataset()

    rechunked = rechunk_for_blockwise(ds, "x", xr.DataArray(labels, dims="x"))
    assert rechunked.foo.chunks == ((5,), expected)


# everything below this is copied from xarray's test_groupby.py
# TODO: chunk these
# TODO: dim=None, dim=Ellipsis, groupby unindexed dim


def test_groupby_duplicate_coordinate_labels(engine):
    # fix for http://stackoverflow.com/questions/38065129
    array = xr.DataArray([1, 2, 3], [("x", [1, 1, 2])])
    expected = xr.DataArray([3, 3], [("x", [1, 2])])
    actual = xarray_reduce(array, array.x, func="sum", engine=engine)
    assert_equal(expected, actual)


def test_multi_index_groupby_sum(engine):
    # regression test for xarray GH873
    ds = xr.Dataset(
        {"foo": (("x", "y", "z"), np.ones((3, 4, 2)))},
        {"x": ["a", "b", "c"], "y": [1, 2, 3, 4]},
    )
    expected = ds.sum("z")
    stacked = ds.stack(space=["x", "y"])
    actual = xarray_reduce(stacked, "space", dim="z", func="sum", engine=engine)
    expected_xarray = stacked.groupby("space").sum("z")
    assert_equal(expected_xarray, actual)
    assert_equal(expected, actual.unstack("space"))

    actual = xarray_reduce(stacked.foo, "space", dim="z", func="sum", engine=engine)
    assert_equal(expected.foo, actual.unstack("space"))

    ds = xr.Dataset(
        dict(a=(("z",), np.ones(10))),
        coords=dict(b=(("z"), np.arange(2).repeat(5)), c=(("z"), np.arange(5).repeat(2))),
    ).set_index(bc=["b", "c"])
    expected = ds.groupby("bc").sum()
    actual = xarray_reduce(ds, "bc", func="sum")
    assert_equal(expected, actual)


@pytest.mark.parametrize("chunks", (None, pytest.param(2, marks=requires_dask)))
def test_xarray_groupby_bins(chunks, engine):
    array = xr.DataArray([1, 1, 1, 1, 1], dims="x")
    labels = xr.DataArray([1, 1.5, 1.9, 2, 3], dims="x", name="labels")

    if chunks:
        array = array.chunk({"x": chunks})
        labels = labels.chunk({"x": chunks})

    kwargs = dict(
        dim="x",
        func="count",
        engine=engine,
        expected_groups=np.array([1, 2, 4, 5]),
        isbin=True,
        fill_value=0,
    )
    with raise_if_dask_computes():
        actual = xarray_reduce(array, labels, **kwargs)
    expected = xr.DataArray(
        np.array([3, 1, 0]),
        dims="labels_bins",
        coords={"labels_bins": [pd.Interval(1, 2), pd.Interval(2, 4), pd.Interval(4, 5)]},
    )
    xr.testing.assert_equal(actual, expected)

    # 3D array, 2D by, single dim, with NaNs in by
    array = array.expand_dims(y=2, z=3)
    labels = labels.expand_dims(y=2).copy()
    labels.data[-1, -1] = np.nan
    with raise_if_dask_computes():
        actual = xarray_reduce(array, labels, **kwargs)
    expected = xr.DataArray(
        np.array([[[3, 1, 0]] * 3, [[3, 0, 0]] * 3]),
        dims=("y", "z", "labels_bins"),
        coords={"labels_bins": [pd.Interval(1, 2), pd.Interval(2, 4), pd.Interval(4, 5)]},
    )
    xr.testing.assert_equal(actual, expected)


@requires_dask
def test_func_is_aggregation():
    from flox.aggregations import mean

    ds = xr.tutorial.open_dataset("rasm", chunks={"time": 9})
    expected = xarray_reduce(ds.Tair, ds.time.dt.month, func="mean")
    actual = xarray_reduce(ds.Tair, ds.time.dt.month, func=mean)
    xr.testing.assert_allclose(actual, expected)

    with pytest.raises(ValueError):
        xarray_reduce(ds.Tair, ds.time.dt.month, func=mean, skipna=True)

    with pytest.raises(ValueError):
        xarray_reduce(ds.Tair, ds.time.dt.month, func=mean, skipna=False)


@requires_dask
def test_cache():
    pytest.importorskip("cachey")

    from flox.cache import cache

    ds = xr.Dataset(
        {
            "foo": (("x", "y"), dask.array.ones((10, 20), chunks=2)),
            "bar": (("x", "y"), dask.array.ones((10, 20), chunks=2)),
        },
        coords={"labels": ("y", np.repeat([1, 2], 10))},
    )

    cache.clear()
    xarray_reduce(ds, "labels", func="mean", method="cohorts")
    assert len(cache.data) == 1

    xarray_reduce(ds, "labels", func="mean", method="blockwise")
    assert len(cache.data) == 2


@requires_dask
@pytest.mark.parametrize("method", ["cohorts", "map-reduce"])
def test_groupby_bins_indexed_coordinate(method):
    ds = (
        xr.tutorial.open_dataset("air_temperature")
        .isel(time=slice(100))
        .chunk({"time": 20, "lat": 5})
    )
    bins = [40, 50, 60, 70]
    expected = ds.groupby_bins("lat", bins=bins).mean(keep_attrs=True, dim=...)
    actual = xarray_reduce(
        ds,
        ds.lat,
        dim=ds.air.dims,
        expected_groups=([40, 50, 60, 70],),
        isbin=(True,),
        func="mean",
        method=method,
    )
    xr.testing.assert_allclose(expected, actual)

    actual = xarray_reduce(
        ds,
        ds.lat,
        dim=ds.air.dims,
        expected_groups=pd.IntervalIndex.from_breaks([40, 50, 60, 70]),
        func="mean",
        method=method,
    )
    xr.testing.assert_allclose(expected, actual)


@pytest.mark.parametrize("chunk", (True, False))
def test_mixed_grouping(chunk):
    if not has_dask and chunk:
        pytest.skip()
    # regression test for https://github.com/xarray-contrib/flox/pull/111
    sa = 10
    sb = 13
    sc = 3

    x = xr.Dataset(
        {
            "v0": xr.DataArray(
                ((np.arange(sa * sb * sc) / sa) % 1).reshape((sa, sb, sc)),
                dims=("a", "b", "c"),
            ),
            "v1": xr.DataArray((np.arange(sa * sb) % 3).reshape(sa, sb), dims=("a", "b")),
        }
    )
    if chunk:
        x["v0"] = x["v0"].chunk({"a": 5})

    r = xarray_reduce(
        x["v0"],
        x["v1"],
        x["v0"],
        expected_groups=(np.arange(6), np.linspace(0, 1, num=5)),
        isbin=[False, True],
        func="count",
        dim="b",
        fill_value=0,
    )
    assert (r.sel(v1=[3, 4, 5]) == 0).all().data


def test_alignment_error():
    da = xr.DataArray(np.arange(10), dims="x", coords={"x": np.arange(10)})
    with pytest.raises(ValueError):
        xarray_reduce(da, da.x.sel(x=slice(5)), func="count")


@pytest.mark.parametrize("add_nan", [True, False])
@pytest.mark.parametrize("dtype_out", [np.float64, "float64", np.dtype("float64")])
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("chunk", (pytest.param(True, marks=requires_dask), False))
def test_dtype(add_nan, chunk, dtype, dtype_out, engine):
    if engine == "numbagg":
        # https://github.com/numbagg/numbagg/issues/121
        pytest.skip()

    xp = dask.array if chunk else np
    data = xp.linspace(0, 1, 48, dtype=dtype).reshape((4, 12))

    if add_nan:
        data[1, ...] = np.nan
        data[0, [0, 2]] = np.nan

    arr = xr.DataArray(
        data,
        dims=("x", "t"),
        coords={
            "labels": ("t", np.array(["a", "a", "c", "c", "c", "b", "b", "c", "c", "b", "b", "f"]))
        },
        name="arr",
    )
    kwargs = dict(func="mean", dtype=dtype_out, engine=engine)
    actual = xarray_reduce(arr, "labels", **kwargs)
    expected = arr.groupby("labels").mean(dtype="float64")

    assert actual.dtype == np.dtype("float64")
    assert actual.compute().dtype == np.dtype("float64")
    xr.testing.assert_allclose(expected, actual, **tolerance64)

    actual = xarray_reduce(arr.to_dataset(), "labels", **kwargs)
    expected = arr.to_dataset().groupby("labels").mean(dtype="float64")

    assert actual.arr.dtype == np.dtype("float64")
    assert actual.compute().arr.dtype == np.dtype("float64")
    xr.testing.assert_allclose(expected, actual.transpose("labels", ...), **tolerance64)


@pytest.mark.parametrize("chunk", [pytest.param(True, marks=requires_dask), False])
@pytest.mark.parametrize("use_flox", [True, False])
def test_dtype_accumulation(use_flox, chunk):
    datetimes = pd.date_range("2010-01", "2015-01", freq="6H", inclusive="left")
    samples = 10 + np.cos(2 * np.pi * 0.001 * np.arange(len(datetimes))) * 1
    samples += np.random.randn(len(datetimes))
    samples = samples.astype("float32")

    nan_indices = np.random.default_rng().integers(0, len(samples), size=5_000)
    samples[nan_indices] = np.nan

    da = xr.DataArray(samples, dims=("time",), coords=[datetimes])
    if chunk:
        da = da.chunk(time=1024)

    gb = da.groupby("time.month")

    with xr.set_options(use_flox=use_flox):
        expected = gb.reduce(np.nanmean)
        actual = gb.mean()
        xr.testing.assert_allclose(expected, actual)
        assert np.issubdtype(actual.dtype, np.float32)
        assert np.issubdtype(actual.compute().dtype, np.float32)

        expected = gb.reduce(np.nanmean, dtype="float64")
        actual = gb.mean(dtype="float64")
        assert np.issubdtype(actual.dtype, np.float64)
        assert np.issubdtype(actual.compute().dtype, np.float64)
        xr.testing.assert_allclose(expected, actual, **tolerance64)


def test_preserve_multiindex():
    """Regression test for GH issue #215"""

    vort = xr.DataArray(
        name="vort",
        data=np.random.uniform(size=(4, 2)),
        dims=["i", "face"],
        coords={"i": ("i", np.arange(4)), "face": ("face", np.arange(2))},
    )

    vort = (
        vort.coarsen(i=2)
        .construct(i=("i_region_coarse", "i_region"))
        .stack(region=["face", "i_region_coarse"])
    )

    bins = [np.linspace(0, 1, 10)]
    bin_intervals = tuple(pd.IntervalIndex.from_breaks(b) for b in bins)

    hist = xarray_reduce(
        xr.DataArray(1),  # weights
        vort,  # variables we want to bin
        func="count",  # count occurrences falling in bins
        expected_groups=bin_intervals,  # bins for each variable
        dim=["i_region"],  # broadcast dimensions
        fill_value=0,  # fill empty bins with 0 counts
    )

    assert "region" in hist.coords


def test_fill_value_xarray_behaviour():
    times = pd.date_range("2000-01-01", freq="6H", periods=10)
    ds = xr.Dataset(
        {
            "bar": (
                "time",
                [1, 2, 3, np.nan, np.nan, np.nan, 4, 5, np.nan, np.nan],
                {"meta": "data"},
            ),
            "time": times,
        }
    )

    pd.date_range("2000-01-01", freq="3H", periods=19)
    with xr.set_options(use_flox=False):
        expected = ds.resample(time="3H").sum()
    with xr.set_options(use_flox=True):
        actual = ds.resample(time="3H").sum()
    xr.testing.assert_identical(expected, actual)


def test_fill_value_xarray_binning():
    array = np.linspace(0, 10, 5 * 10, dtype=int).reshape(5, 10)

    x = np.array([0, 0, 1, 2, 2])
    y = np.arange(array.shape[1]) * 3
    u = np.linspace(0, 1, 5)

    data_array = xr.DataArray(data=array, coords={"x": x, "y": y, "u": ("x", u)}, dims=("x", "y"))
    with xr.set_options(use_flox=False):
        expected = data_array.groupby_bins("y", bins=4).mean()
    with xr.set_options(use_flox=True):
        actual = data_array.groupby_bins("y", bins=4).mean()

    xr.testing.assert_identical(expected, actual)
