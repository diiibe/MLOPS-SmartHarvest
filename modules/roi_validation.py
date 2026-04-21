"""
ROI polygon validation — runs before any GEE call so that malformed input
fails fast with a clear message instead of crashing deep inside the pipeline
or silently producing nonsense.

Checks (in order):
  1. Structural: outer ring is a list of [lon, lat] pairs, ≥ 4 vertices,
     and the ring is closed (first == last).
  2. Coordinate bounds: lon ∈ [-180, 180], lat ∈ [-90, 90].
  3. Antimeridian crossing: reject if the ring spans ≥ 180° of longitude
     (not supported by GEE without explicit splitting).
  4. Self-intersection: rejected via a shapely validity check.
  5. Area: rejected if greater than `max_area_ha` (default from config).

Returns the GeoJSON-style coordinates unchanged if valid; raises
`ROIValidationError` with a human-readable message otherwise.
"""

from __future__ import annotations

from typing import List, Sequence


class ROIValidationError(ValueError):
    """Raised when an ROI polygon fails structural or geographic checks."""


def _as_rings(coords) -> List[List[List[float]]]:
    """Accept either `[[[lon,lat],...]]` (polygon) or `[[lon,lat],...]` (bare ring)."""
    if not isinstance(coords, (list, tuple)) or not coords:
        raise ROIValidationError("ROI coordinates must be a non-empty list.")
    first = coords[0]
    if first and isinstance(first[0], (int, float)):
        # Bare ring [[lon,lat],...] — wrap to polygon shape.
        return [list(coords)]
    return [list(ring) for ring in coords]


def _check_ring(ring: Sequence[Sequence[float]]) -> None:
    if len(ring) < 4:
        raise ROIValidationError(
            f"Polygon ring must have at least 4 vertices (got {len(ring)})."
        )
    for i, vertex in enumerate(ring):
        if len(vertex) < 2:
            raise ROIValidationError(
                f"Vertex {i} has fewer than 2 coordinates: {vertex!r}"
            )
        lon, lat = vertex[0], vertex[1]
        if not (-180.0 <= lon <= 180.0):
            raise ROIValidationError(
                f"Vertex {i} longitude {lon} out of range [-180, 180]."
            )
        if not (-90.0 <= lat <= 90.0):
            raise ROIValidationError(
                f"Vertex {i} latitude {lat} out of range [-90, 90]."
            )
    if ring[0][:2] != ring[-1][:2]:
        raise ROIValidationError(
            "Polygon ring is not closed (first vertex must equal last)."
        )


def _lon_span(ring: Sequence[Sequence[float]]) -> float:
    lons = [v[0] for v in ring]
    return max(lons) - min(lons)


def _polygon_area_m2(ring: Sequence[Sequence[float]]) -> float:
    """Approximate area in m² using shapely on WGS84 coordinates, projected
    locally. For validation we only need order-of-magnitude accuracy — enough
    to catch "user drew a polygon covering the whole country" mistakes."""
    try:
        from shapely.geometry import Polygon
    except ImportError:
        return 0.0  # shapely missing → skip the area check silently

    poly = Polygon([(v[0], v[1]) for v in ring])
    if not poly.is_valid:
        return 0.0

    # Rough equal-area: scale longitude by cos(mean latitude), then treat
    # as metres via WGS84 mean radius. 1° latitude ≈ 111_320 m.
    import math

    mean_lat = sum(v[1] for v in ring) / len(ring)
    lon_scale = math.cos(math.radians(mean_lat)) * 111_320.0
    lat_scale = 111_320.0
    scaled = Polygon([(v[0] * lon_scale, v[1] * lat_scale) for v in ring])
    return float(scaled.area)


def validate_roi_coords(coords, max_area_ha: float = 10_000.0):
    """
    Validate a GeoJSON polygon coordinate list. Returns the normalized
    polygon coordinates `[[[lon,lat],...]]` on success; raises
    `ROIValidationError` on failure.
    """
    rings = _as_rings(coords)
    outer = rings[0]
    _check_ring(outer)

    span = _lon_span(outer)
    if span >= 180.0:
        raise ROIValidationError(
            f"ROI spans {span:.1f}° of longitude — likely crossing the "
            "antimeridian. Split the polygon into two parts (east and west of "
            "±180°) and run them separately."
        )

    # Self-intersection check (requires shapely; skip if unavailable)
    try:
        from shapely.geometry import Polygon

        poly = Polygon([(v[0], v[1]) for v in outer])
        if not poly.is_valid:
            raise ROIValidationError(
                f"ROI polygon is invalid: {poly.is_valid_reason if hasattr(poly, 'is_valid_reason') else 'self-intersecting or degenerate'}"
            )
    except ImportError:
        pass

    area_m2 = _polygon_area_m2(outer)
    if area_m2 > 0:
        area_ha = area_m2 / 10_000.0
        if area_ha > max_area_ha:
            raise ROIValidationError(
                f"ROI area {area_ha:.0f} ha exceeds the {max_area_ha:.0f} ha "
                "limit. Split the polygon into smaller tiles or raise "
                "SMARTHARVEST_MAX_ROI_HA."
            )

    return rings
