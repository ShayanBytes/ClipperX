"""
layout.py - output-canvas geometry for the N-way split grid.

`grid_cells(n, out_w, out_h)` returns the list of output sub-rectangles (x, y, w, h) that
a SPLIT plan's cells map onto, in slot order. It is the single source of truth shared by the
crop planner (which needs each cell's aspect ratio to crop a matching region from the source)
and the renderer (which pastes each rendered cell into its rectangle). Keeping it in one place
means the two can never disagree on the grid.

Layouts (vertical 9:16 output):
  n=1  full frame
  n=2  two equal rows (top / bottom)          - the original 2-way split
  n=3  two cells on top + one wide cell below
  n=4  2x2 quad
"""
from __future__ import annotations

from typing import List, Tuple

Rect = Tuple[int, int, int, int]  # (x, y, w, h) in output pixels


def grid_cells(n: int, out_w: int, out_h: int) -> List[Rect]:
    n = max(1, min(4, int(n)))
    half_w = out_w // 2
    half_h = out_h // 2
    if n == 1:
        return [(0, 0, out_w, out_h)]
    if n == 2:
        return [(0, 0, out_w, half_h),
                (0, half_h, out_w, out_h - half_h)]
    if n == 3:
        return [(0, 0, half_w, half_h),
                (half_w, 0, out_w - half_w, half_h),
                (0, half_h, out_w, out_h - half_h)]
    # n == 4 -> 2x2 quad
    return [(0, 0, half_w, half_h),
            (half_w, 0, out_w - half_w, half_h),
            (0, half_h, half_w, out_h - half_h),
            (half_w, half_h, out_w - half_w, out_h - half_h)]
