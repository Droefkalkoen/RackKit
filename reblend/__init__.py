"""RE-Blend — Blender extension for Rack Extension GUI sprite-sheet production.

Makes the Blender scene the single source of truth for a Rack Extension's 2D
GUI art: control states bound to timeline frames, per-element cameras derived
from registration empties, verified straight-alpha sprite-sheet export, and
two-way sync with the RE project's ``GUI2D/*.lua`` configuration.

This package must stay importable *outside* Blender: the ``project`` layer
(Lua reading/writing, palette, manifest) is pure Python and is exercised by
the test suite without ``bpy``. Anything that needs Blender imports ``bpy``
lazily inside the modules that use it.
"""

__version__ = "0.1.0"


def register() -> None:
    """Blender extension entry point.

    Operators, panels, and property registration land here as they are
    implemented (design §8). Kept as a no-op so the extension loads cleanly
    while only the Blender-independent layers exist.
    """


def unregister() -> None:
    """Blender extension exit point (mirror of :func:`register`)."""


def cli() -> None:
    """Headless entry point (design §7).

    Invoked as::

        blender -b MyDevice.blend --python-expr "import reblend; reblend.cli()" -- \\
            render --all --project /path/to/mydevice --strict

    Implemented in M3; defined now so the invocation contract is stable.
    """
    raise NotImplementedError("headless CLI arrives in milestone M3")
