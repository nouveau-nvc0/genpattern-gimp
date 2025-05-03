from typing import Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

class ProgressWindow(Gtk.Dialog):
    _progress_bar: Gtk.ProgressBar
    _progress_format: str
    _finish_value: Optional[int]
    _pulse_timeout_id: Optional[int]

    def __init__(self, title: str, progress_format: str, finish_value: Optional[int] = None):
        Gtk.Dialog.__init__(self, title=title, transient_for=None, modal=True)

        self._progress_format = progress_format

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)

        if finish_value is not None:
            self._finish_value = finish_value
            self._progress_bar.set_text(self._progress_format.format(0, self._finish_value))
        else:
            self._progress_bar.set_text(self._progress_format)
            self._pulse_timeout_id = GLib.timeout_add(100, self._pulse_cb)        

        self.get_content_area().pack_start(self._progress_bar, True, True, 0)
        self.set_default_size(300, 50)

    def update_value(self, new_value: int) -> None:
        assert self._finish_value is not None and new_value <= self._finish_value

        fraction = new_value / self._finish_value
        self._progress_bar.set_fraction(fraction)
        self._progress_bar.set_text(self._progress_format.format(new_value, self._finish_value))
        while Gtk.events_pending():
            Gtk.main_iteration()

    def _pulse_cb(self) -> bool:
        self._progress_bar.pulse()
        while Gtk.events_pending():
            Gtk.main_iteration()
        return True
       
    def do_dispose(self) -> None:
        if self._pulse_timeout_id is not None:
            GLib.source_remove(self._pulse_timeout_id)
        Gtk.Dialog.do_dispose(self)

    def show(self) -> None:
        self.show_all()
        while Gtk.events_pending():
            Gtk.main_iteration()
    