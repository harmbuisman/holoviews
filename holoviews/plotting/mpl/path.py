from __future__ import absolute_import, division, unicode_literals

import param
import numpy as np

from matplotlib.dates import date2num, DateFormatter
from matplotlib.collections import PatchCollection, LineCollection

from ...core import util
from ...core.dimension import Dimension
from ...core.options import abbreviated_exception
from ...element import Polygons
from .element import ColorbarPlot
from .util import polygons_to_path_patches


class PathPlot(ColorbarPlot):

    aspect = param.Parameter(default='square', doc="""
        PathPlots axes usually define single space so aspect of Paths
        follows aspect in data coordinates by default.""")

    show_legend = param.Boolean(default=False, doc="""
        Whether to show legend for the plot.""")

    style_opts = ['alpha', 'color', 'linestyle', 'linewidth', 'visible', 'cmap']

    def get_data(self, element, ranges, style):
        with abbreviated_exception():
            style = self._apply_transforms(element, ranges, style)

        style_mapping = any(True for v in style.values() if isinstance(v, util.arraylike_types))
        dims = element.kdims
        xdim, ydim = dims
        generic_dt_format = Dimension.type_formatters[np.datetime64]
        paths, cvals, dims = [], [], {}
        for path in element.split(datatype='columns'):
            xarr, yarr = path[xdim.name], path[ydim.name]
            if util.isdatetime(xarr):
                dt_format = Dimension.type_formatters.get(type(xarr[0]), generic_dt_format)
                xarr = date2num(xarr)
                dims[0] = xdim(value_format=DateFormatter(dt_format))
            if util.isdatetime(yarr):
                dt_format = Dimension.type_formatters.get(type(yarr[0]), generic_dt_format)
                yarr = date2num(yarr)
                dims[1] = ydim(value_format=DateFormatter(dt_format))
            arr = np.column_stack([xarr, yarr])
            if not style_mapping:
                paths.append(arr)
                continue
            length = len(xarr)
            for (s1, s2) in zip(range(length-1), range(1, length+1)):
                paths.append(arr[s1:s2+1])
        if self.invert_axes:
            paths = [p[::-1] for p in paths]
        if not style_mapping:
            return (paths,), style, {'dimensions': dims}
        if 'c' in style:
            style['array'] = style.pop('c')
        if 'vmin' in style:
            style['clim'] = style.pop('vmin', None), style.pop('vmax', None)
        return (paths,), style, {'dimensions': dims}

    def init_artists(self, ax, plot_args, plot_kwargs):
        line_segments = LineCollection(*plot_args, **plot_kwargs)
        ax.add_collection(line_segments)
        return {'artist': line_segments}

    def update_handles(self, key, axis, element, ranges, style):
        artist = self.handles['artist']
        data, style, axis_kwargs = self.get_data(element, ranges, style)
        artist.set_paths(data[0])
        if 'array' in style:
            artist.set_array(style['array'])
            artist.set_clim(style['clim'])
        if 'norm' in style:
            artist.set_norm(style['norm'])
        artist.set_visible(style.get('visible', True))
        if 'colors' in style:
            artist.set_edgecolors(style['colors'])
        if 'facecolors' in style:
            artist.set_facecolors(style['facecolors'])
        if 'linewidth' in style:
            artist.set_linewidths(style['linewidth'])
        return axis_kwargs


class ContourPlot(PathPlot):

    def init_artists(self, ax, plot_args, plot_kwargs):
        line_segments = LineCollection(*plot_args, **plot_kwargs)
        ax.add_collection(line_segments)
        return {'artist': line_segments}

    def get_data(self, element, ranges, style):
        if isinstance(element, Polygons):
            color_prop = 'facecolors'
            subpaths = polygons_to_path_patches(element)
            paths = [path for subpath in subpaths for path in subpath]
            if self.invert_axes:
                for p in paths:
                    p._path.vertices = p._path.vertices[:, ::-1]
        else:
            color_prop = 'colors'
            paths = element.split(datatype='array', dimensions=element.kdims)
            if self.invert_axes:
                paths = [p[:, ::-1] for p in paths]

        # Process style transform
        with abbreviated_exception():
            style = self._apply_transforms(element, ranges, style)

        if 'c' in style:
            style['array'] = style.pop('c')
            style['clim'] = style.pop('vmin'), style.pop('vmax')
        elif isinstance(style.get('color'), np.ndarray):
            style[color_prop] = style.pop('color')

        return (paths,), style, {}


class PolygonPlot(ContourPlot):
    """
    PolygonPlot draws the polygon paths in the supplied Polygons
    object. If the Polygon has an associated value the color of
    Polygons will be drawn from the supplied cmap, otherwise the
    supplied facecolor will apply. Facecolor also determines the color
    for non-finite values.
    """

    show_legend = param.Boolean(default=False, doc="""
        Whether to show legend for the plot.""")

    style_opts = ['alpha', 'cmap', 'facecolor', 'edgecolor', 'linewidth',
                  'hatch', 'linestyle', 'joinstyle', 'fill', 'capstyle',
                  'color']

    def init_artists(self, ax, plot_args, plot_kwargs):
        polys = PatchCollection(*plot_args, **plot_kwargs)
        ax.add_collection(polys)
        return {'artist': polys}
