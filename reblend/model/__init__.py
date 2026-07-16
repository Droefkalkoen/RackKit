"""Model layer: RE Element schema, state tables, rig generators, calibration.

Everything here except :mod:`reblend.model.rigs` is pure Python and testable
without ``bpy``; ``rigs`` applies the pure descriptions to a live Blender
scene and imports ``bpy`` lazily.
"""
