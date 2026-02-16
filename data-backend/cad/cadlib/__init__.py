"""CAD library for Remote CAD - ThAssembly and ThBody for hierarchical model building."""

from .assembly import ThBody, ThAssembly
from .materials import MATERIAL_LIBRARY, get_material, list_materials
from .profile import ThProfile
from .path import ThPath
from .saw import hand_saw, saw_cut

__all__ = [
    "ThBody",
    "ThAssembly",
    "ThProfile",
    "ThPath",
    "hand_saw",
    "saw_cut",
    "MATERIAL_LIBRARY",
    "get_material",
    "list_materials",
]
