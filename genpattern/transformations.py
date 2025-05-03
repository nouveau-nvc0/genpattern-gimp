import random
import math

from dict_over_bytes_property import DictOverBytesProperty
from genpattern_lib import GPImgAlpha
from i18n import _
from progress_window import ProgressWindow

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp, Gegl, GLib

def _transform_layer(layer: Gimp.Layer, scale: float, angle: float) -> Gimp.Layer:
    image = layer.get_image()
    t_layer = layer.copy()
    t_layer.set_name(f"{layer.get_name()} transformed")
    image.insert_layer(t_layer, None, 0)
    width = t_layer.get_width()
    height = t_layer.get_height()
    cx, cy = width / 2.0, height / 2.0
    t_layer.transform_2d(cx, cy, scale, scale, angle, cx, cy)
    return t_layer


def _extract_alpha(layer: Gimp.Layer) -> tuple[int, int, bytes]:
    buffer = layer.get_buffer()
    width = layer.get_width()
    height = layer.get_height()
    rect = Gegl.Rectangle.new(0, 0, width, height)
    pixels = buffer.get(rect, 1.0, None, Gegl.AbyssPolicy.NONE)
    alpha_data = bytearray()
    for i in range(3, len(pixels), 4):
        alpha_data.append(pixels[i])
    return width, height, bytes(alpha_data)

def perform_transformations(image: Gimp.Image,
                            layer_copies_default: int,
                            layer_copies: DictOverBytesProperty[int, int],
                            layer_max_angle: DictOverBytesProperty[int, int],
                            layer_max_scale: DictOverBytesProperty[int, float],
                            max_angle: int,
                            max_scale: float,
                            random_seed: int) -> tuple[list[Gimp.Layer], list[list[GPImgAlpha]], list[Gimp.Layer]]:
    Gimp.Selection.none(image)
    rng = random.Random(random_seed)
    orig_layers = list(image.get_layers())
    if not orig_layers:
        msg = _("Image does not contain any layers.")
        error = GLib.Error.new_literal(Gimp.PlugIn.error_quark(), msg, 0)
        raise RuntimeError(error.message)

    collections = []
    transformed_layers = []
    total_copies = 0
    for layer in orig_layers:
        if not layer.has_alpha():
            continue
        layer_tattoo = layer.get_tattoo()
        copies_count = layer_copies.get(layer_tattoo, layer_copies_default)
        total_copies += copies_count

    progress_window = ProgressWindow(_("Preparing images..."),
                                     _("Preparing images: {} of {}"),
                                     total_copies)
    progress_window.show()

    counter = 0
    for layer in orig_layers:
        if not layer.has_alpha():
            continue
        layer_tattoo = layer.get_tattoo()
        copies_count = layer_copies.get(layer_tattoo, layer_copies_default)
        max_angle_for_layer = layer_max_angle.get(layer_tattoo, max_angle)
        max_scale_for_layer = layer_max_scale.get(layer_tattoo, max_scale)
        max_angle_radians = math.radians(max_angle_for_layer)
        col = []
        for i in range(copies_count):
            scale = rng.uniform(1.0, max_scale_for_layer)
            angle = rng.uniform(-max_angle_radians, max_angle_radians)
            t_layer = _transform_layer(layer, scale, angle)
            w, h, alpha_bytes = _extract_alpha(t_layer)
            gp_img = GPImgAlpha(w, h, alpha_bytes)
            col.append(gp_img)
            transformed_layers.append(t_layer)
            counter += 1
            progress_window.update_value(counter)
        collections.append(col)
    progress_window.destroy()
    return orig_layers, collections, transformed_layers
