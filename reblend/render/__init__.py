"""Render layer: batch render, strip stitching, output validation (§5).

:mod:`stitcher` and :mod:`validators` are pure numpy and testable without
Blender; :mod:`bpy_io` and :mod:`renderer` drive a live Blender scene and
import ``bpy`` lazily.
"""
