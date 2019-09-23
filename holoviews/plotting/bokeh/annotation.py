from __future__ import absolute_import, division, unicode_literals

from collections import defaultdict

import param
import numpy as np
from bokeh.models import Span, Arrow, Div as BkDiv
try:
    from bokeh.models.arrow_heads import TeeHead, NormalHead
    arrow_start = {'<->': NormalHead, '<|-|>': NormalHead}
    arrow_end = {'->': NormalHead, '-[': TeeHead, '-|>': NormalHead,
                 '-': None}
except:
    from bokeh.models.arrow_heads import OpenHead, NormalHead
    arrow_start = {'<->': NormalHead, '<|-|>': NormalHead}
    arrow_end = {'->': NormalHead, '-[': OpenHead, '-|>': NormalHead,
                 '-': None}
from bokeh.transform import dodge

from ...core.util import datetime_types, dimension_sanitizer, basestring
from ...element import HLine, VLine
from ..plot import GenericElementPlot
from .element import AnnotationPlot, ElementPlot, CompositeElementPlot, ColorbarPlot
from .styles import text_properties, line_properties
from .plot import BokehPlot
from .util import date_to_integer


class TextPlot(ElementPlot, AnnotationPlot):

    style_opts = text_properties+['color', 'angle', 'visible']
    _plot_methods = dict(single='text', batched='text')

    def get_data(self, element, ranges, style):
        mapping = dict(x='x', y='y', text='text')
        if self.static_source:
            return dict(x=[], y=[], text=[]), mapping, style
        if self.invert_axes:
            data = dict(x=[element.y], y=[element.x])
        else:
            data = dict(x=[element.x], y=[element.y])
        self._categorize_data(data, ('x', 'y'), element.dimensions())
        data['text'] = [element.text]
        if 'text_align' not in style:
            style['text_align'] = element.halign
        baseline = 'middle' if element.valign == 'center' else element.valign
        if 'text_baseline' not in style:
            style['text_baseline'] = baseline
        if 'text_font_size' not in style:
            style['text_font_size'] = '%dPt' % element.fontsize
        if 'color' in style:
            style['text_color'] = style.pop('color')
        style['angle'] = np.deg2rad(style.get('angle', element.rotation))
        return (data, mapping, style)

    def get_batched_data(self, element, ranges=None):
        data = defaultdict(list)
        zorders = self._updated_zorders(element)
        for (key, el), zorder in zip(element.data.items(), zorders):
            style = self.lookup_options(element.last, 'style')
            style = style.max_cycles(len(self.ordering))[zorder]
            eldata, elmapping, style = self.get_data(el, ranges, style)
            for k, eld in eldata.items():
                data[k].extend(eld)
        return data, elmapping, style

    def get_extents(self, element, ranges=None, range_type='combined'):
        return None, None, None, None



class LabelsPlot(ColorbarPlot, AnnotationPlot):

    show_legend = param.Boolean(default=False, doc="""
        Whether to show legend for the plot.""")

    xoffset = param.Number(default=None, doc="""
      Amount of offset to apply to labels along x-axis.""")

    yoffset = param.Number(default=None, doc="""
      Amount of offset to apply to labels along x-axis.""")

    style_opts = text_properties + ['cmap', 'angle', 'visible']

    _nonvectorized_styles = ['cmap']

    _plot_methods = dict(single='text', batched='text')
    _batched_style_opts = text_properties

    def get_data(self, element, ranges, style):
        style = self.style[self.cyclic_index]
        if 'angle' in style and isinstance(style['angle'], (int, float)):
            style['angle'] = np.deg2rad(style.get('angle', 0))

        dims = element.dimensions()
        coords = (1, 0) if self.invert_axes else (0, 1)
        xdim, ydim, tdim = (dimension_sanitizer(dims[i].name) for i in coords+(2,))
        mapping = dict(x=xdim, y=ydim, text=tdim)
        data = {d: element.dimension_values(d) for d in (xdim, ydim)}
        if self.xoffset is not None:
            mapping['x'] = dodge(xdim, self.xoffset)
        if self.yoffset is not None:
            mapping['y'] = dodge(ydim, self.yoffset)
        data[tdim] = [dims[2].pprint_value(v) for v in element.dimension_values(2)]
        self._categorize_data(data, (xdim, ydim), element.dimensions())
        return data, mapping, style



class LineAnnotationPlot(ElementPlot, AnnotationPlot):

    style_opts = line_properties + ['level', 'visible']

    apply_ranges = param.Boolean(default=False, doc="""
        Whether to include the annotation in axis range calculations.""")

    _plot_methods = dict(single='Span')

    def get_data(self, element, ranges, style):
        data, mapping = {}, {}
        dim = 'width' if isinstance(element, HLine) else 'height'
        if self.invert_axes:
            dim = 'width' if dim == 'height' else 'height'
        mapping['dimension'] = dim
        loc = element.data
        if isinstance(loc, datetime_types):
            loc = date_to_integer(loc)
        mapping['location'] = loc
        return (data, mapping, style)

    def _init_glyph(self, plot, mapping, properties):
        """
        Returns a Bokeh glyph object.
        """
        box = Span(level=properties.get('level', 'glyph'), **mapping)
        plot.renderers.append(box)
        return None, box

    def get_extents(self, element, ranges=None, range_type='combined'):
        loc = element.data
        if isinstance(element, VLine):
            dim = 'x'
        elif isinstance(element, HLine):
            dim = 'y'
        if self.invert_axes:
            dim = 'x' if dim == 'y' else 'x'
        ranges[dim]['soft'] = loc, loc
        return super(LineAnnotationPlot, self).get_extents(element, ranges, range_type)



class SplinePlot(ElementPlot, AnnotationPlot):
    """
    Draw the supplied Spline annotation (see Spline docstring).
    Does not support matplotlib Path codes.
    """

    style_opts = line_properties + ['visible']
    _plot_methods = dict(single='bezier')

    def get_data(self, element, ranges, style):
        if self.invert_axes:
            data_attrs = ['y0', 'x0', 'cy0', 'cx0', 'cy1', 'cx1', 'y1', 'x1']
        else:
            data_attrs = ['x0', 'y0', 'cx0', 'cy0', 'cx1', 'cy1', 'x1', 'y1']
        verts = np.array(element.data[0])
        inds = np.where(np.array(element.data[1])==1)[0]
        data = {da: [] for da in data_attrs}
        skipped = False
        for vs in np.split(verts, inds[1:]):
            if len(vs) != 4:
                skipped = len(vs) > 1
                continue
            for x, y, xl, yl in zip(vs[:, 0], vs[:, 1], data_attrs[::2], data_attrs[1::2]):
                data[xl].append(x)
                data[yl].append(y)
        if skipped:
            self.param.warning(
                'Bokeh SplitPlot only support cubic splines, unsupported '
                'splines were skipped during plotting.')
        data = {da: data[da] for da in data_attrs}
        return (data, dict(zip(data_attrs, data_attrs)), style)



class ArrowPlot(CompositeElementPlot, AnnotationPlot):

    style_opts = (['arrow_%s' % p for p in line_properties+['size']] + text_properties)

    _style_groups = {'arrow': 'arrow', 'label': 'text'}

    def get_data(self, element, ranges, style):
        plot = self.state
        label_mapping = dict(x='x', y='y', text='text')

        # Compute arrow
        x1, y1 = element.x, element.y
        axrange = plot.x_range if self.invert_axes else plot.y_range
        span = (axrange.end - axrange.start) / 6.
        if element.direction == '^':
            x2, y2 = x1, y1-span
            label_mapping['text_baseline'] = 'top'
        elif element.direction == '<':
            x2, y2 = x1+span, y1
            label_mapping['text_align'] = 'left'
            label_mapping['text_baseline'] = 'middle'
        elif element.direction == '>':
            x2, y2 = x1-span, y1
            label_mapping['text_align'] = 'right'
            label_mapping['text_baseline'] = 'middle'
        else:
            x2, y2 = x1, y1+span
            label_mapping['text_baseline'] = 'bottom'
        arrow_opts = {'x_end': x1, 'y_end': y1,
                      'x_start': x2, 'y_start': y2}

        # Define arrowhead
        arrow_opts['arrow_start'] = arrow_start.get(element.arrowstyle, None)
        arrow_opts['arrow_end'] = arrow_end.get(element.arrowstyle, NormalHead)

        # Compute label
        if self.invert_axes:
            label_data = dict(x=[y2], y=[x2])
        else:
            label_data = dict(x=[x2], y=[y2])
        label_data['text'] = [element.text]
        return ({'label': label_data},
                {'arrow': arrow_opts, 'label': label_mapping}, style)


    def _init_glyph(self, plot, mapping, properties, key):
        """
        Returns a Bokeh glyph object.
        """
        properties.pop('legend', None)
        if key == 'arrow':
            properties.pop('source')
            arrow_end = mapping.pop('arrow_end')
            arrow_start = mapping.pop('arrow_start')
            start = arrow_start(**properties) if arrow_start else None
            end = arrow_end(**properties) if arrow_end else None
            renderer = Arrow(start=start, end=end, **dict(**mapping))
            glyph = renderer
        else:
            properties = {p if p == 'source' else 'text_'+p: v
                          for p, v in properties.items()}
            renderer, glyph = super(ArrowPlot, self)._init_glyph(
                plot, mapping, properties, 'text_1')
        plot.renderers.append(renderer)
        return renderer, glyph

    def get_extents(self, element, ranges=None, range_type='combined'):
        return None, None, None, None



class DivPlot(BokehPlot, GenericElementPlot, AnnotationPlot):

    height = param.Number(default=300)

    width = param.Number(default=300)

    finalize_hooks = param.HookList(default=[], doc="""
        Deprecated; use hooks options instead.""")

    hooks = param.HookList(default=[], doc="""
        Optional list of hooks called when finalizing a plot. The
        hook is passed the plot object and the displayed element, and
        other plotting handles can be accessed via plot.handles.""")

    _stream_data = False

    def __init__(self, element, plot=None, **params):
        super(DivPlot, self).__init__(element, **params)
        self.callbacks = []
        self.handles = {} if plot is None else self.handles['plot']
        self.static = len(self.hmap) == 1 and len(self.keys) == len(self.hmap)

    def get_data(self, element, ranges, style):
        return element.data, {}, style


    def initialize_plot(self, ranges=None, plot=None, plots=None, source=None):
        """
        Initializes a new plot object with the last available frame.
        """
        # Get element key and ranges for frame
        element = self.hmap.last
        key = self.keys[-1]
        self.current_frame = element
        self.current_key = key

        data, _, _ = self.get_data(element, ranges, {})
        div = BkDiv(text=data, width=self.width, height=self.height)
        self.handles['plot'] = div
        self._execute_hooks(element)
        self.drawn = True
        return div


    def update_frame(self, key, ranges=None, plot=None):
        """
        Updates an existing plot with data corresponding
        to the key.
        """
        element = self._get_frame(key)
        text, _, _ = self.get_data(element, ranges, {})
        self.handles['plot'].text = text
