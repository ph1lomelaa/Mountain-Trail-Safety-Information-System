"""
Import real Almaty trails and POIs from OpenStreetMap (Overpass API) into mountain.db.

Usage:
    python scripts/import_almaty_osm.py
    python scripts/import_almaty_osm.py --bbox "43.00,76.75,43.35,77.30"
    python scripts/import_almaty_osm.py --append
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import time
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import h3


DEFAULT_BBOX = (43.00, 76.75, 43.35, 77.30)  # south, west, north, east
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_H3_RESOLUTION = 7


def parse_bbox(raw_bbox: str) -> Tuple[float, float, float, float]:
    parts = [p.strip() for p in raw_bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("BBOX must have 4 comma-separated numbers: south,west,north,east")
    south, west, north, east = (float(v) for v in parts)
    if south >= north:
        raise ValueError("BBOX invalid: south must be less than north")
    if west >= east:
        raise ValueError("BBOX invalid: west must be less than east")
    return south, west, north, east


def overpass_bbox(bbox: Tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    return f"{south},{west},{north},{east}"


def overpass_request(query: str, overpass_url: str, max_retries: int = 4) -> Dict:
    for attempt in range(1, max_retries + 1):
        try:
            encoded = urlencode({"data": query}).encode("utf-8")
            request = Request(
                overpass_url,
                data=encoded,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urlopen(request, timeout=240) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == max_retries:
                raise RuntimeError(f"Overpass request failed after {max_retries} attempts: {exc}") from exc
            time.sleep(attempt * 2)
        except Exception as exc:  # noqa: BLE001
            if attempt == max_retries:
                raise RuntimeError(f"Overpass request failed after {max_retries} attempts: {exc}") from exc
            time.sleep(attempt * 2)
    raise RuntimeError("Unexpected retry loop exit")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def polyline_length_km(path: Sequence[Tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        lat1, lon1 = path[i]
        lat2, lon2 = path[i + 1]
        total += haversine_km(lat1, lon1, lat2, lon2)
    return total


def infer_difficulty(tags: Dict[str, str]) -> str:
    sac_scale = (tags.get("sac_scale") or "").strip().lower()
    sac_map = {
        "hiking": "easy",
        "mountain_hiking": "moderate",
        "demanding_mountain_hiking": "hard",
        "alpine_hiking": "extreme",
        "demanding_alpine_hiking": "extreme",
        "difficult_alpine_hiking": "extreme",
    }
    if sac_scale in sac_map:
        return sac_map[sac_scale]

    visibility = (tags.get("trail_visibility") or "").strip().lower()
    if visibility in {"poor", "horrible", "bad"}:
        return "hard"

    incline = (tags.get("incline") or "").replace("%", "").strip()
    if incline:
        try:
            incline_value = abs(float(incline))
            if incline_value >= 20:
                return "hard"
            if incline_value >= 10:
                return "moderate"
        except ValueError:
            pass

    highway = (tags.get("highway") or "").strip().lower()
    if highway == "track":
        return "moderate"
    if highway in {"path", "bridleway", "footway"}:
        return "easy"

    return "moderate"


def should_keep_way(way_id: int, tags: Dict[str, str], hiking_relation_way_ids: set[int]) -> bool:
    if way_id in hiking_relation_way_ids:
        return True

    highway = (tags.get("highway") or "").strip().lower()
    if highway not in {"path", "track", "footway", "bridleway"}:
        return False

    if (tags.get("access") or "").strip().lower() == "private":
        return False

    if highway == "footway" and (tags.get("footway") or "").strip().lower() in {"sidewalk", "crossing", "link"}:
        return False

    if (tags.get("area") or "").strip().lower() == "yes":
        return False

    return True


def build_trails_query(bbox: Tuple[float, float, float, float]) -> str:
    bbox_str = overpass_bbox(bbox)
    return f"""
[out:json][timeout:240];
(
  relation["route"="hiking"]({bbox_str});
  way["highway"~"path|track|footway|bridleway"]["access"!="private"]({bbox_str});
);
(._;>;);
out body;
"""


def build_pois_query(bbox: Tuple[float, float, float, float]) -> str:
    bbox_str = overpass_bbox(bbox)
    return f"""
[out:json][timeout:180];
(
  node["amenity"~"cafe|restaurant|shelter|drinking_water"]({bbox_str});
  way["amenity"~"cafe|restaurant|shelter|drinking_water"]({bbox_str});
  node["tourism"~"viewpoint|camp_site|alpine_hut|wilderness_hut"]({bbox_str});
  way["tourism"~"viewpoint|camp_site|alpine_hut|wilderness_hut"]({bbox_str});
  node["natural"="spring"]({bbox_str});
  way["natural"="spring"]({bbox_str});
);
out center;
"""


def map_poi_category(tags: Dict[str, str]) -> Optional[str]:
    amenity = (tags.get("amenity") or "").strip().lower()
    tourism = (tags.get("tourism") or "").strip().lower()
    natural = (tags.get("natural") or "").strip().lower()

    if amenity == "cafe":
        return "cafe"
    if amenity == "restaurant":
        return "restaurant"
    if amenity == "shelter" or tourism in {"alpine_hut", "wilderness_hut"}:
        return "shelter"
    if tourism == "viewpoint":
        return "viewpoint"
    if amenity == "drinking_water" or natural == "spring":
        return "water_source"
    if tourism == "camp_site":
        return "campsite"
    return None


def extract_lat_lon(element: Dict) -> Optional[Tuple[float, float]]:
    if element.get("type") == "node":
        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)

    center = element.get("center")
    if not center:
        return None
    lat = center.get("lat")
    lon = center.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def build_trail_rows(
    trail_payload: Dict,
    h3_resolution: int,
    min_length_km: float,
) -> List[Tuple]:
    elements = trail_payload.get("elements", [])

    nodes: Dict[int, Tuple[float, float]] = {}
    ways: List[Dict] = []
    hiking_relation_way_ids: set[int] = set()

    for el in elements:
        el_type = el.get("type")
        if el_type == "node":
            nodes[el["id"]] = (float(el["lat"]), float(el["lon"]))
        elif el_type == "way":
            ways.append(el)
        elif el_type == "relation":
            tags = el.get("tags", {})
            if (tags.get("route") or "").strip().lower() != "hiking":
                continue
            for member in el.get("members", []):
                if member.get("type") == "way" and member.get("ref"):
                    hiking_relation_way_ids.add(int(member["ref"]))

    rows: List[Tuple] = []
    seen_source_ids = set()

    for way in ways:
        way_id = int(way["id"])
        tags = way.get("tags", {})
        if not should_keep_way(way_id, tags, hiking_relation_way_ids):
            continue

        source_id = f"way:{way_id}"
        if source_id in seen_source_ids:
            continue

        path: List[Tuple[float, float]] = []
        for node_id in way.get("nodes", []):
            point = nodes.get(int(node_id))
            if point:
                path.append(point)

        if len(path) < 2:
            continue

        length_km = polyline_length_km(path)
        if length_km < min_length_km:
            continue

        name = (tags.get("name") or "").strip() or f"OSM Trail {way_id}"
        difficulty = infer_difficulty(tags)

        ascent_raw = (tags.get("ascent") or tags.get("ele") or "").replace("m", "").strip()
        elevation_gain_m = 0.0
        if ascent_raw:
            try:
                elevation_gain_m = abs(float(ascent_raw))
            except ValueError:
                elevation_gain_m = 0.0

        start_lat, start_lng = path[0]
        end_lat, end_lng = path[-1]
        h3_index = h3.geo_to_h3(start_lat, start_lng, h3_resolution)

        geometry_json = json.dumps(
            {
                "type": "LineString",
                "coordinates": [[lng, lat] for lat, lng in path],
            },
            ensure_ascii=False,
        )

        description_parts = [
            f"Imported from OSM way {way_id}",
            f"highway={tags.get('highway', 'unknown')}",
        ]
        if tags.get("sac_scale"):
            description_parts.append(f"sac_scale={tags['sac_scale']}")
        description = "; ".join(description_parts)

        rows.append(
            (
                name,
                description,
                difficulty,
                round(length_km, 3),
                round(elevation_gain_m, 2),
                start_lat,
                start_lng,
                end_lat,
                end_lng,
                h3_index,
                h3_resolution,
                geometry_json,
                "osm",
                source_id,
            )
        )
        seen_source_ids.add(source_id)

    return rows


def build_poi_rows(poi_payload: Dict, h3_resolution: int) -> List[Tuple]:
    rows: List[Tuple] = []
    seen_source_ids = set()

    for el in poi_payload.get("elements", []):
        source_type = el.get("type")
        if source_type not in {"node", "way"}:
            continue

        tags = el.get("tags", {})
        category = map_poi_category(tags)
        if not category:
            continue

        lat_lon = extract_lat_lon(el)
        if not lat_lon:
            continue

        lat, lng = lat_lon
        source_id = f"{source_type}:{el['id']}"
        if source_id in seen_source_ids:
            continue

        name = (tags.get("name") or "").strip() or f"OSM {category.replace('_', ' ').title()} {el['id']}"
        description = tags.get("description") or f"Imported from OSM {source_id}"
        h3_index = h3.geo_to_h3(lat, lng, h3_resolution)

        rows.append(
            (
                name,
                category,
                description,
                lat,
                lng,
                h3_index,
                None,
                "osm",
                source_id,
            )
        )
        seen_source_ids.add(source_id)

    return rows


def validate_schema(conn: sqlite3.Connection) -> None:
    trail_cols = {row[1] for row in conn.execute("PRAGMA table_info(trails)").fetchall()}
    poi_cols = {row[1] for row in conn.execute("PRAGMA table_info(pois)").fetchall()}

    required_trail_cols = {"geometry_json", "source", "source_id", "h3_resolution"}
    required_poi_cols = {"source", "source_id"}

    if not required_trail_cols.issubset(trail_cols):
        missing = sorted(required_trail_cols - trail_cols)
        raise RuntimeError(f"trails table missing columns: {', '.join(missing)}")
    if not required_poi_cols.issubset(poi_cols):
        missing = sorted(required_poi_cols - poi_cols)
        raise RuntimeError(f"pois table missing columns: {', '.join(missing)}")


def import_rows(
    conn: sqlite3.Connection,
    trail_rows: Sequence[Tuple],
    poi_rows: Sequence[Tuple],
    replace: bool,
) -> None:
    if replace:
        conn.execute("DELETE FROM pois WHERE source = 'osm'")
        conn.execute("DELETE FROM trails WHERE source = 'osm'")

    if trail_rows:
        conn.executemany(
            """
            INSERT INTO trails (
                name, description, difficulty, length_km, elevation_gain_m,
                start_lat, start_lng, end_lat, end_lng,
                h3_index, h3_resolution, geometry_json,
                source, source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            trail_rows,
        )

    if poi_rows:
        conn.executemany(
            """
            INSERT INTO pois (
                name, category, description, latitude, longitude,
                h3_index, trail_id, source, source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            poi_rows,
        )

    conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import OSM Almaty map data into mountain.db")
    parser.add_argument(
        "--db",
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mountain.db"),
        help="Path to SQLite database (default: ./mountain.db)",
    )
    parser.add_argument(
        "--bbox",
        default=",".join(str(v) for v in DEFAULT_BBOX),
        help="Bounding box as south,west,north,east",
    )
    parser.add_argument(
        "--overpass-url",
        default=DEFAULT_OVERPASS_URL,
        help="Overpass API endpoint",
    )
    parser.add_argument(
        "--h3-resolution",
        type=int,
        default=DEFAULT_H3_RESOLUTION,
        help="H3 resolution for imported entities",
    )
    parser.add_argument(
        "--min-trail-length-km",
        type=float,
        default=0.2,
        help="Drop tiny way fragments shorter than this value",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append OSM rows instead of replacing previous OSM import",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bbox = parse_bbox(args.bbox)

    if not os.path.exists(args.db):
        raise FileNotFoundError(f"Database not found: {args.db}. Run `python init_db.py` first.")

    print("Fetching trails from Overpass...")
    trails_payload = overpass_request(build_trails_query(bbox), args.overpass_url)
    print("Fetching POIs from Overpass...")
    pois_payload = overpass_request(build_pois_query(bbox), args.overpass_url)

    trail_rows = build_trail_rows(trails_payload, args.h3_resolution, args.min_trail_length_km)
    poi_rows = build_poi_rows(pois_payload, args.h3_resolution)

    conn = sqlite3.connect(args.db)
    try:
        validate_schema(conn)
        import_rows(conn, trail_rows, poi_rows, replace=not args.append)
    finally:
        conn.close()

    print("Import complete")
    print(f"  Trails imported: {len(trail_rows)}")
    print(f"  POIs imported:   {len(poi_rows)}")
    print(f"  BBOX:            {bbox}")
    print(f"  H3 resolution:   {args.h3_resolution}")


if __name__ == "__main__":
    main()
