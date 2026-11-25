"""Adapter registry: houses.json names an adapter by string; this maps it to a class.

Add a platform = write sources/<name>.py and add one line here. Modules are imported lazily,
so a house whose adapter is not written yet is skipped (not a crash).
"""
import importlib

# name -> "module:ClassName"  (module is relative to this package)
ADAPTERS = {
    "example_html": "example_html:ExampleHtmlAdapter",
    # GoAuction platform: Lay's, McTear's, Anderson & Garland, Mallams, Halls (docs/SOURCES.md).
    "goauction": "goauction:GoAuctionAdapter",
    # White-label catalogue platform (auctions.<house>/catalogue/<hash>/<hash>/<slug>/): Gardiner Houlgate, Fieldings,
    # Mellors & Kirk, Trevanion, Peter Francis, Hansons.
    "whitelabel": "whitelabel:WhiteLabelAdapter",
    # Planned (see docs/SOURCES.md). Not written yet.
    "gorringes": "gorringes:GorringesAdapter",
    "lawrences": "lawrences:LawrencesAdapter",
    "easylive": "easylive:EasyLiveAdapter",
    "duggleby": "duggleby:DugglebyAdapter",
    "roseberys": "roseberys:RoseberysAdapter",
    "rogersjones": "rogersjones:RogersJonesAdapter",
}


class AdapterNotAvailable(Exception):
    pass


def get_adapter(name):
    """Return the adapter class registered under `name`."""
    if name not in ADAPTERS:
        raise AdapterNotAvailable(f"unknown adapter '{name}'")
    module, cls = ADAPTERS[name].split(":")
    try:
        mod = importlib.import_module("." + module, __package__)
    except ModuleNotFoundError as err:
        if err.name and err.name.endswith(module):
            raise AdapterNotAvailable(f"adapter '{name}' is not written yet") from err
        raise
    return getattr(mod, cls)
