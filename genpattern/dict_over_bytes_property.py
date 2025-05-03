import gi
gi.require_version('Gimp', '3.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gimp, GLib, GObject

import pickle
from typing import Iterable, TypeVar, Generic, Dict

_K = TypeVar('_K')
_V = TypeVar('_V')

class DictOverBytesProperty(GObject.GObject, Generic[_K, _V]):
    __gtype_name__ = 'DictOverBytesProperty'
    __gsignals__ = {
        'changed-externally': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    _storage: Dict[_K, _V]
    _property: str
    _config: Gimp.ProcedureConfig
    _just_changed: bool = False

    def __init__(self, config: Gimp.ProcedureConfig, bytes_property_name: str):
        GObject.GObject.__init__(self)
        self._property = bytes_property_name
        self._config = config
        self._load()
        config.connect(f'notify::{bytes_property_name}', self._load)

    def _load(self, config: Gimp.ProcedureConfig | None = None,
              param_spec: GObject.ParamSpec | None = None) -> None:
        if self._just_changed:
            self._just_changed = False
            return
        gbytes: GLib.Bytes = self._config.get_property(self._property)
        if gbytes:
            data = gbytes.get_data()
            if data:
                self._storage = pickle.loads(data)
                self.emit('changed-externally')
                return
        self._storage = {}
        self.emit('changed-externally')

    def _commit(self) -> None:
        data = pickle.dumps(self._storage)
        gbytes = GLib.Bytes.new(data)
        self._just_changed = True
        self._config.set_property(self._property, gbytes)

    def __getitem__(self, key: _K) -> _V:
        return self._storage[key]

    def __setitem__(self, key: _K, value: _V) -> None:
        self._storage[key] = value
        self._commit()

    def __delitem__(self, key: _K) -> None:
        del self._storage[key]
        self._commit()

    def __contains__(self, key: _K) -> bool:
        return key in self._storage

    def get(self, key: _K, default: _V) -> _V:
        return self._storage.get(key, default)

    def keys(self) -> Iterable[_K]:
        return self._storage.keys()

    def values(self) -> Iterable[_V]:
        return self._storage.values()

    def items(self) -> Iterable[tuple[_K, _V]]:
        return self._storage.items()
