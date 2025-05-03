from dataclasses import dataclass, field
from typing import Generic, TypeVar

import gi
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, GObject, GLib

from dict_over_bytes_property import DictOverBytesProperty
from i18n import _

_K = TypeVar('_K')
_V = TypeVar('_V')
@dataclass
class _PerLayerProperty(Generic[_K, _V]):
    name: str
    value: DictOverBytesProperty[_K, _V]
    list_store_idx: int
    values_type: type
    _control: GimpUi.SpinButton | None = field(init=False, default=None)

    @property
    def control(self) -> GimpUi.SpinButton:
        assert self._control is not None
        return self._control

    @control.setter
    def control(self, control: GimpUi.SpinButton) -> None:
        self._control = control

class GenPatternDialog(GimpUi.ProcedureDialog):
    _config: Gimp.ProcedureConfig
    _image: Gimp.Image

    _layer_copies: _PerLayerProperty[int, int]
    _layer_max_angle: _PerLayerProperty[int, int]
    _layer_max_scale: _PerLayerProperty[int, float]

    _layer_property_by_name: dict[str, _PerLayerProperty] = dict()

    _layer_list_store: Gtk.ListStore
    _layer_icon_view: Gtk.IconView

    def __init__(self,
                 procedure: Gimp.Procedure,
                 image: Gimp.Image,
                 config: Gimp.ProcedureConfig,
                 layer_copies: DictOverBytesProperty[int, int],
                 layer_max_angle: DictOverBytesProperty[int, int],
                 layer_max_scale: DictOverBytesProperty[int, float]):
        GimpUi.ProcedureDialog.__init__(self, procedure=procedure, config=config)
        
        self._config = config
        self._image = image

        self._config.connect('notify', self._on_default_layer_config_changed)

        content_area = self.get_content_area()
        self.set_size_request(600, -1)

        layer_frame = Gtk.Frame(hexpand=True)
        layer_grid = Gtk.Grid(column_spacing=10, row_spacing=2, hexpand=True)
        layer_frame.add(layer_grid)

        self._layer_copies = _PerLayerProperty('copies', layer_copies, 3, int)
        self._layer_copies.control = self._setup_layer_spin_button(self._layer_copies,
                                                                   _('Number of copies:'),
                                                                   1, GLib.MAXINT, layer_grid, 0)
        
        self._layer_max_angle = _PerLayerProperty('max-angle', layer_max_angle, 4, int)
        self._layer_max_angle.control = self._setup_layer_spin_button(self._layer_max_angle,
                                                                      _('Max rotation angle (degrees):'),
                                                                      0, 180, layer_grid, 1)
        
        self._layer_max_scale = _PerLayerProperty('max-scale', layer_max_scale, 5, float)
        self._layer_max_scale.control = self._setup_layer_spin_button(self._layer_max_scale,
                                                                      _('Max scale factor:'),
                                                                      1, GLib.MAXDOUBLE, layer_grid, 2,
                                                                      0.1, 1.0, 1)

        scrolled = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.AUTOMATIC, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                      min_content_height=250, hexpand=True)
        layer_grid.attach(scrolled, 0, 3, 2, 1)

        # ListStore: [pixbuf, layer name, layer tattoo, copies count, max angle, max scale].
        self._layer_list_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, GObject.TYPE_UINT,
                                               GObject.TYPE_INT, GObject.TYPE_UINT, GObject.TYPE_DOUBLE)
        self._layer_icon_view = Gtk.IconView(model=self._layer_list_store, pixbuf_column=0, text_column=1,
                                             item_padding=0, item_width=80)
        scrolled.add(self._layer_icon_view)

        icon_theme = Gtk.IconTheme.get_default()
        default_pixbuf = icon_theme.load_icon('image-missing-symbolic', 80, Gtk.IconLookupFlags.FORCE_SIZE)
    
        default_iter = self._layer_list_store.append([
            default_pixbuf,
            _('Default'),
            GLib.MAXUINT,
            config.get_property('copies'),
            config.get_property('max-angle'),
            config.get_property('max-scale')
        ])
        self._layer_icon_view.select_path(self._layer_list_store.get_path(default_iter))

        for layer in self._image.get_layers():
            if not layer.has_alpha():
                continue
            pixbuf = layer.get_thumbnail(80, 80, Gimp.PixbufTransparency.KEEP_ALPHA)
            layer_name = layer.get_name()
            layer_tattoo = layer.get_tattoo()
            self._layer_list_store.append([pixbuf,
                                           layer_name,
                                           layer_tattoo,
                                           self._layer_copies.value.get(layer_tattoo, self._config.get_property('copies')),
                                           self._layer_max_angle.value.get(layer_tattoo, self._config.get_property('max-angle')),
                                           self._layer_max_scale.value.get(layer_tattoo, self._config.get_property('max-scale'))])

        self._layer_icon_view.connect('selection-changed', self._on_iconview_selection_changed)

        content_area.pack_start(layer_frame, True, True, 0)

        self.get_widget('threshold', GimpUi.SpinScale)
        self.get_widget('sch-param', GimpUi.SpinScale)
        std_box = self.fill_box('std_args', ['threshold', 'offset-radius', 'coll-offset-radius',
                                             'sch-type', 'sch-param', 'seed'])
        content_area.pack_start(std_box, False, False, 0)

    def _setup_layer_spin_button(self,
                                 property: _PerLayerProperty,
                                 label: str,
                                 lower: float,
                                 upper: float,
                                 grid: Gtk.Grid,
                                 row: int,
                                 step_increment: float = 1.0,
                                 page_increment: float = 10.0,
                                 digits: int = 0) -> GimpUi.SpinButton:
        adjustment = Gtk.Adjustment(value=self._config.get_property(property.name),
                                    lower=lower, upper=upper, step_increment=step_increment,
                                    page_increment=page_increment, page_size=0)
        spin_button = GimpUi.SpinButton(adjustment=adjustment, climb_rate=1, digits=digits,
                                        value=self._config.get_property(property.name))
        spin_button.connect('value-changed', self._on_spin_button_value_changed, property)
        
        label_widget = Gtk.Label(label=label, halign=Gtk.Align.START)
        
        grid.attach(label_widget, 0, row, 1, 1)
        grid.attach(spin_button, 1, row, 1, 1)

        self._layer_property_by_name[property.name] = property
        property.value.connect('changed-externally',
                               self._on_per_layer_property_changed_externally, property)

        return spin_button

    def _get_layer_icon_view_selected(self) -> Gtk.TreeIter | None:
        selected = self._layer_icon_view.get_selected_items()
        if selected:
            tree_iter = self._layer_list_store.get_iter(selected[0])
            if tree_iter:
                return tree_iter 
        return None

    def _on_iconview_selection_changed(self, iconview: Gtk.IconView) -> None:
        tree_iter = self._get_layer_icon_view_selected()
        if tree_iter is not None:
            for property in self._layer_property_by_name.values():
                current_value = self._layer_list_store.get_value(tree_iter, property.list_store_idx)
                property.control.set_value(current_value)
        else:
            default_iter = self._layer_list_store.get_iter_first()
            assert default_iter is not None
            self._layer_icon_view.select_path(self._layer_list_store.get_path(default_iter))

    def _on_spin_button_value_changed(self, spin_button: GimpUi.SpinButton, property: _PerLayerProperty) -> None:
        tree_iter = self._get_layer_icon_view_selected()
        if tree_iter is None:
            return
        
        new_value = property.values_type(spin_button.get_value())

        layer_tattoo = self._layer_list_store.get_value(tree_iter, 2)
        self._layer_list_store.set_value(tree_iter, property.list_store_idx, new_value)
        if layer_tattoo == GLib.MAXUINT:
            # Update global property.
            self._config.set_property(property.name, new_value)
        else:
            if new_value == self._config.get_property(property.name):
                if layer_tattoo in property.value:
                    del property.value[layer_tattoo]
            else:
                property.value[layer_tattoo] = new_value

    def _get_selected_idx(self) -> int | None:
        tree_iter = self._get_layer_icon_view_selected()
        if tree_iter:
            result = self._layer_list_store.get_value(tree_iter, 2)
            assert type(result) is int
            return result
        return None

    def _on_default_layer_config_changed(self, config: Gimp.ProcedureConfig,
                                         param_spec: GObject.ParamSpec) -> None:
        property_name = param_spec.name
        property = self._layer_property_by_name.get(property_name)
        if property is None:
            return
        new_default = config.get_property(property_name)
        
        current_idx = self._get_selected_idx()
        if current_idx == GLib.MAXUINT and property.control.get_value() != new_default:
            property.control.set_value(new_default)

        for item in self._layer_list_store:
            if item[2] not in property.value:
                item[property.list_store_idx] = new_default

    def _on_per_layer_property_changed_externally(self,
                                                  property_dict: DictOverBytesProperty,
                                                  property: _PerLayerProperty) -> None:
        current_idx = self._get_selected_idx()
        
        for item in self._layer_list_store:
            value = property.value.get(item[2], None)
            if value is None:
                value = self._config.get_property(property.name)
            item[property.list_store_idx] = value

            if item[2] == current_idx:
                property.control.set_value(value)
