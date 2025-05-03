import os
import gettext

_SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
_CATALOG = gettext.Catalog('genpattern', os.path.join(_SCRIPT_PATH, 'locale'), fallback=True)

def _(message: str) -> str:
    return _CATALOG.gettext(message)
