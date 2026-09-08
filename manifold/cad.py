"""Single CAD import boundary, including the tested Windows DLL load order."""
import sys

if sys.platform == 'win32':
    # With pinned CasADi/NLopt wheels, importing NLopt first causes Windows heap
    # corruption during interpreter shutdown. Load CasADi before CadQuery imports
    # its sketch (NLopt) module. Do not hide failed exit codes or skip cleanup.
    import casadi as _casadi

import cadquery as cq
