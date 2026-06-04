from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple


Point = Tuple[float, float]
Polygon = Sequence[Sequence[float]]


def normalize_point(x: float, y: float, width: float, height: float) -> Point:
    if width <= 0 or height <= 0:
        return 0.0, 0.0
    return max(0.0, min(1.0, x / width)), max(0.0, min(1.0, y / height))


def footpoint_xyxy(box: Sequence[float]) -> Point:
    x1, y1, x2, y2 = box[:4]
    return (float(x1 + x2) / 2.0, float(y2))


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, current in enumerate(polygon):
        xi, yi = float(current[0]), float(current[1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def locate_zone(point: Point, zones: Iterable[dict]) -> Optional[dict]:
    for zone in zones:
        polygon = zone.get("polygon") or []
        if polygon and point_in_polygon(point, polygon):
            return zone
    return None


def line_side(point: Point, line: Sequence[Sequence[float]]) -> float:
    (x1, y1), (x2, y2) = line
    return (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)


def crossed_line(previous: Optional[Point], current: Point, line: Sequence[Sequence[float]]) -> Optional[str]:
    if previous is None:
        return None
    old_side = line_side(previous, line)
    new_side = line_side(current, line)
    if old_side == 0 or new_side == 0 or old_side * new_side > 0:
        return None
    return "above_to_below" if old_side < new_side else "below_to_above"
