import itertools

import param
import numpy as np

from ..core import Dataset, OrderedDict
from ..core.operation import ElementOperation
from ..core.util import pd, is_nan, sort_topologically, cartesian_product

try:
    import dask
except:
    dask = None

try:
    import xarray as xr
except:
    xr = None


def toarray(v, index_value=False):
    """
    Interface helper function to turn dask Arrays into numpy arrays as
    necessary. If index_value is True, a value is returned instead of
    an array holding a single value.
    """
    if dask and isinstance(v, dask.array.Array):
        arr =  v.compute()
        return arr[()] if index_value else arr
    else:
        return v

def compute_edges(edges):
    """
    Computes edges from a number of bin centers,
    throwing an exception if the edges are not
    evenly spaced.
    """
    widths = np.diff(edges)
    if np.allclose(widths, widths[0]):
        width = widths[0]
    else:
        raise ValueError('Centered bins have to be of equal width.')
    edges -= width/2.
    return np.concatenate([edges, [edges[-1]+width]])


def reduce_fn(x):
    """
    Aggregation function to get the first non-zero value.
    """
    values = x.values if pd and isinstance(x, pd.Series) else x
    for v in values:
        if not is_nan(v):
            return v
    return np.NaN


class categorical_aggregate2d(ElementOperation):
    """
    Generates a gridded Dataset of 2D aggregate arrays indexed by the
    first two dimensions of the passed Element, turning all remaining
    dimensions into value dimensions. The key dimensions of the
    gridded array are treated as categorical indices. Useful for data
    indexed by two independent categorical variables such as a table
    of population values indexed by country and year. Data that is
    indexed by continuous dimensions should be binned before
    aggregation. The aggregation will retain the global sorting order
    of both dimensions.

    >> table = Table([('USA', 2000, 282.2), ('UK', 2005, 58.89)],
                     kdims=['Country', 'Year'], vdims=['Population'])
    >> categorical_aggregate2d(table)
    Dataset({'Country': ['USA', 'UK'], 'Year': [2000, 2005],
             'Population': [[ 282.2 , np.NaN], [np.NaN,   58.89]]},
            kdims=['Country', 'Year'], vdims=['Population'])
    """

    datatype = param.List(['xarray', 'grid'] if xr else ['grid'], doc="""
        The grid interface types to use when constructing the gridded Dataset.""")

    def _process(self, obj, key=None):
        """
        Generates a categorical 2D aggregate by inserting NaNs at all
        cross-product locations that do not already have a value assigned.
        Returns a 2D gridded Dataset object.
        """
        if isinstance(obj, Dataset) and obj.interface.gridded:
            return obj
        elif obj.ndims > 2:
            raise ValueError("Cannot aggregate more than two dimensions")
        elif len(obj.dimensions()) < 3:
            raise ValueError("Must have at two dimensions to aggregate over"
                             "and one value dimension to aggregate on.")

        dim_labels = obj.dimensions(label=True)
        dims = obj.dimensions()
        kdims, vdims = dims[:2], dims[2:]
        xdim, ydim = dim_labels[:2]
        nvdims = len(dims) - 2
        d1keys = obj.dimension_values(xdim, False)
        d2keys = obj.dimension_values(ydim, False)
        shape = (len(d2keys), len(d1keys))
        nsamples = np.product(shape)

        # Determine global orderings of y-values using topological sort
        grouped = obj.groupby(xdim, container_type=OrderedDict,
                              group_type=Dataset).values()
        orderings = OrderedDict()
        is_sorted = np.array_equal(np.sort(d1keys), d1keys)
        for group in grouped:
            vals = group.dimension_values(ydim)
            if len(vals) == 1:
                orderings[vals[0]] = []
            else:
                is_sorted &= np.array_equal(np.sort(vals), vals)
                for i in range(len(vals)-1):
                    p1, p2 = vals[i:i+2]
                    orderings[p1] = [p2]
        if is_sorted:
            d2keys = np.sort(d2keys)
        else:
            d2keys = list(itertools.chain(*sort_topologically(orderings)))

        # Pad data with NaNs
        ys, xs = cartesian_product([d2keys, d1keys])
        data = {xdim: xs.flatten(), ydim: ys.flatten()}
        for vdim in vdims:
            values = np.empty(nsamples)
            values[:] = np.NaN
            data[vdim.name] = values
        dtype = 'dataframe' if pd else 'dictionary'
        dense_data = Dataset(data, kdims=obj.kdims, vdims=obj.vdims, datatype=[dtype])
        concat_data = obj.interface.concatenate([dense_data, Dataset(obj)], datatype=dtype)
        agg = concat_data.reindex([xdim, ydim]).aggregate([xdim, ydim], reduce_fn)

        # Convert data to a gridded dataset
        grid_data = {xdim: d1keys, ydim: d2keys}
        for vdim in vdims:
            grid_data[vdim.name] = agg.dimension_values(vdim).reshape(shape)
        return agg.clone(grid_data, datatype=self.p.datatype)

