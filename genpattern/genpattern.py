#!/usr/bin/env python3
import sys

from dict_over_bytes_property import DictOverBytesProperty
from genpattern_dialog import GenPatternDialog
from progress_window import ProgressWindow
from transformations import perform_transformations
from genpattern_lib import GPImgAlpha, gp_genpattern, GPExponentialSchedule, GPLinearSchedule
from i18n import _

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp, GLib
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

class GenPatternPlugin(Gimp.PlugIn):
    _config: Gimp.ProcedureConfig
    _layer_copies: DictOverBytesProperty[int, int]
    _layer_max_angle: DictOverBytesProperty[int, int]
    _layer_max_scale: DictOverBytesProperty[int, float]

    def do_set_i18n(self, _: str) -> tuple[bool, str, None]:
        return True, 'gimp30-python', None

    def do_query_procedures(self) -> list[str]:
        return ['plug-in-genpattern']

    def do_create_procedure(self, procedure_name: str) -> Gimp.ImageProcedure:
        procedure = Gimp.ImageProcedure.new(self, procedure_name, Gimp.PDBProcType.PLUGIN, self._run, None)
        procedure.set_image_types('*')
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE)
        procedure.set_menu_label(_('Random pattern...'))
        procedure.set_icon_name('gimp')
        procedure.add_menu_path('<Image>/Filters/Artistic/')
        procedure.set_documentation(
            _('Generate a random seamless patterned texture from layers with transparency using libgenpattern.'),
            _('Uses libgenpattern to compose a seamless patterned texture from transformed layers.'),
            procedure_name)
        procedure.set_attribution('Arkadii Chekha', 'Arkadii Chekha', '2025')
        
        procedure.add_int_argument('copies', _('Copies per layer (default)'), _('Copies per layer (default)'),
                                     1, GLib.MAXINT, 5, GObject.ParamFlags.READWRITE)
        procedure.add_int_argument('threshold', _('Alpha channel threshold'), _('Alpha channel threshold'),
                                     1, 255, 64, GObject.ParamFlags.READWRITE)
        procedure.add_int_argument('offset-radius', _('Min distance'), _('Minimum distance between two layers'),
                                     0, GLib.MAXINT, 5, GObject.ParamFlags.READWRITE)
        procedure.add_int_argument('coll-offset-radius', _('Min distance (same layer copies)'),
                                   _('Minimum distance between two layers in the same collection'),
                                     0, GLib.MAXINT, 20, GObject.ParamFlags.READWRITE)
        
        schedule_choice = Gimp.Choice()
        schedule_choice.add('Linear', 0, _('Linear'), 'Linear cooling schedule')
        schedule_choice.add('Exponential', 1, _('Exponential'), 'Exponential cooling schdeule')
        procedure.add_choice_argument('sch-type', _('Cooling schedule type'), _('Cooling schedule type'), 
                                      schedule_choice, 'Exponential', GObject.ParamFlags.READWRITE)
        
        procedure.add_double_argument('sch-param', _('Cooling schedule param'), _('Cooling schedule param'),
                                      0.00001, 0.99999, 0.9, GObject.ParamFlags.READWRITE)
        procedure.add_int_argument('max-angle', _('Max rotation angle'), _('Max rotation angle'),
                                   0, 180, 60, GObject.ParamFlags.READWRITE)
        procedure.add_double_argument('max-scale', _('Max scale factor'), _('Max scale factor'),
                                      0.0, GLib.MAXDOUBLE, 3.0, GObject.ParamFlags.READWRITE)
        procedure.add_int_argument('seed', _('Random seed'), _('Random seed'),
                                     0, min(GLib.MAXINT, GLib.MAXUINT32), 42, GObject.ParamFlags.READWRITE)
        
        procedure.add_bytes_argument('copies-per-layer', _('Pickle buffer'),
                                     _('Pickle buffer containig layer tattoo id to configured number of copies map'),
                                     GObject.ParamFlags.READWRITE)
        procedure.set_argument_sync('copies-per-layer', Gimp.ArgumentSync.PARASITE)

        procedure.add_bytes_argument('max-angle-per-layer', _('Pickle buffer'),
                                _('Pickle buffer containig layer tattoo id to configured max angle map'),
                                GObject.ParamFlags.READWRITE)
        procedure.set_argument_sync('max-angle-per-layer', Gimp.ArgumentSync.PARASITE)

        procedure.add_bytes_argument('max-scale-per-layer', _('Pickle buffer'),
                                _('Pickle buffer containig layer tattoo id to configured max scale factor map'),
                                GObject.ParamFlags.READWRITE)
        procedure.set_argument_sync('max-scale-per-layer', Gimp.ArgumentSync.PARASITE)

        return procedure
    
    def _run(self, procedure: Gimp.Procedure,
             run_mode: Gimp.RunMode,
             image: Gimp.Image,
             drawables: list[Gimp.Drawable],
             config: Gimp.ProcedureConfig,
             data: object | None) -> Gimp.ValueArray:
        self._config = config
        self._layer_copies = DictOverBytesProperty(config, 'copies-per-layer')
        self._layer_max_angle = DictOverBytesProperty(config, 'max-angle-per-layer')
        self._layer_max_scale = DictOverBytesProperty(config, 'max-scale-per-layer')
        
        if run_mode == Gimp.RunMode.INTERACTIVE:
            GimpUi.init('plug-in-genpattern-ui')
            
            dialog = GenPatternDialog(procedure, image, config, self._layer_copies, self._layer_max_angle, self._layer_max_scale)
            dialog.show_all()
            if not dialog.run():
                dialog.destroy()
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
            else:
                dialog.destroy()

        Gimp.context_push()
        image.undo_group_start()

        orig_layers, collections, transformed_layers = perform_transformations(image,
                                                                               config.get_property('copies'),
                                                                               self._layer_copies,
                                                                               self._layer_max_angle,
                                                                               self._layer_max_scale,
                                                                               config.get_property('max-angle'),
                                                                               config.get_property('max-scale'),
                                                                               config.get_property('seed'))
        self._start(image, orig_layers, collections, transformed_layers)
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    def _place_images(self,
                      image: Gimp.Image,
                      orig_layers: list[Gimp.Layer],
                      transformed_layers: list[Gimp.Layer],
                      result: list[list[list[tuple[int, int]]]]) -> None:
        total_placements = 0
        for col in result:
            for coords in col:
                if coords:
                    total_placements += len(coords)
        if total_placements == 0:
            total_placements = 1

        placement_window = ProgressWindow(_('Placing images...'),
                                          _('Placing images: {} of {}'),
                                          total_placements)
        placement_window.show()

        counter = 0
        idx = 0
        for col in result:
            for coords in col:
                t_layer = transformed_layers[idx]
                idx += 1
                if not coords:
                    if t_layer in image.get_layers():
                        image.remove_layer(t_layer)
                else:
                    first = True
                    for (x, y) in coords:
                        if first:
                            t_layer.set_offsets(x, y)
                            first = False
                        else:
                            copy_layer = t_layer.copy()
                            copy_layer.set_offsets(x, y)
                            image.insert_layer(copy_layer, None, 0)
                        counter += 1
                        placement_window.update_value(counter)
        placement_window.destroy()
        for layer in orig_layers:
            if layer in image.get_layers():
                image.remove_layer(layer)

    def _start(self,
               image: Gimp.Image,
               orig_layers: list[Gimp.Layer],
               collections: list[list[GPImgAlpha]],
               transformed_layers: list[Gimp.Layer]) -> None:
        canvas_w = image.get_width()
        canvas_h = image.get_height()

        schedule: GPExponentialSchedule | GPLinearSchedule
        if self._config.get_property('sch-type') == 'Exponential':
            schedule = GPExponentialSchedule(self._config.get_property('sch-param'))
        else:
            schedule = GPLinearSchedule(self._config.get_property('sch-param'))

        progress_window = ProgressWindow(_('Generating pattern...'), _('Generating pattern...'))
        progress_window.show()
        
        main_loop = GLib.MainLoop()

        def worker(argument: None) -> None:
            res = None
            try:
                res = gp_genpattern(collections, canvas_w, canvas_h,
                                    self._config.get_property('threshold'), self._config.get_property('offset-radius'),
                                    self._config.get_property('coll-offset-radius'), schedule, self._config.get_property('seed'))
            except Exception as e:
                exception_text = str(e)
                self._error_msg(_('Error in gp_genpattern: {}').format(exception_text))
            GLib.idle_add(on_genpattern_complete, res)
            return None

        def on_genpattern_complete(result: list[list[list[tuple[int, int]]]] | None) -> bool:
            if result is not None:
                self._place_images(image, orig_layers, transformed_layers, result)
            Gimp.displays_flush()
            progress_window.destroy()
            Gimp.Selection.none(image)
            image.undo_group_end()
            Gimp.context_pop()
            main_loop.quit()
            return False

        GLib.Thread.new('gp_genpattern_worker', worker, None)
        main_loop.run()

    @staticmethod
    def _error_msg(msg: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=None,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=_('Error')
        )
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()

Gimp.main(GenPatternPlugin.__gtype__, sys.argv)
