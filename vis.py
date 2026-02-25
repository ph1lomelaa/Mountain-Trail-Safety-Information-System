"""
H3 Map Visualizer — generates an HTML map showing all H3 cells from the database.
Requires: pip install h3
Usage: python vis.py
Opens a map in your browser with all trails, POIs, and check-ins visualized as H3 hexagons.

Display resolution: 9 (~0.11 km² per cell, ~49x smaller than stored res-7 cells).
Trail routes are drawn from stored geometry when available.
"""
import sqlite3
import os
import json
import webbrowser

try:
    import h3
except ImportError:
    print("❌ Please install h3: pip install h3")
    exit(1)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mountain.db")
if not os.path.exists(DB_PATH):
    print("❌ Database not found. Run 'python init_db.py' first.")
    exit(1)

# Resolution for display — 9 gives very precise hexagons (~0.17 km edge, ~0.1 km² per cell)
DISPLAY_RES = 9
DISPLAY_HEX_AREA_KM2 = h3.hex_area(DISPLAY_RES, unit="km^2")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Collect data — include end coords for trails so we can draw the route
trails = [dict(r) for r in conn.execute(
    "SELECT name, h3_index, start_lat, start_lng, end_lat, end_lng, difficulty, geometry_json FROM trails"
).fetchall()]
pois = [dict(r) for r in conn.execute(
    "SELECT name, h3_index, latitude, longitude, category FROM pois"
).fetchall()]
checkins = [dict(r) for r in conn.execute(
    "SELECT sc.id, sc.h3_index, sc.latitude, sc.longitude, sc.status, u.username "
    "FROM safety_checkins sc JOIN users u ON sc.user_id = u.id WHERE sc.status IN ('active','overdue')"
).fetchall()]
events = [dict(r) for r in conn.execute(
    "SELECT title, h3_index, location_lat, location_lng FROM events"
).fetchall()]
conn.close()


def h3_to_geojson_polygon(h3_index, properties):
    boundary = h3.h3_to_geo_boundary(h3_index, geo_json=True)
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [list(boundary) + [boundary[0]]]
        }
    }


def resolve_cell_for_display(h3_index=None, lat=None, lng=None):
    """
    Return a valid H3 cell at DISPLAY_RES.
    Prefer coordinates when available so upsampling (e.g., res-7 -> res-9) is always valid.
    """
    if lat is not None and lng is not None:
        return h3.geo_to_h3(lat, lng, DISPLAY_RES)

    if not h3_index:
        return None

    source_res = h3.h3_get_resolution(h3_index)
    if source_res == DISPLAY_RES:
        return h3_index
    if source_res > DISPLAY_RES:
        return h3.h3_to_parent(h3_index, DISPLAY_RES)

    # For lower-resolution source cells, pick a deterministic child.
    return h3.h3_to_center_child(h3_index, DISPLAY_RES)


def read_trail_path_points(trail):
    geometry_json = trail.get("geometry_json")
    if geometry_json:
        try:
            geom = json.loads(geometry_json)
            if geom.get("type") == "LineString":
                points = []
                for lng, lat in geom.get("coordinates", []):
                    points.append((lat, lng))
                if len(points) >= 2:
                    return points
        except (TypeError, ValueError, KeyError):
            pass

    return [
        (trail["start_lat"], trail["start_lng"]),
        (trail["end_lat"], trail["end_lng"]),
    ]


def compute_route_cells_from_points(path_points, resolution):
    if len(path_points) < 2:
        return []

    cells = []
    seen = set()
    for i in range(len(path_points) - 1):
        start_lat, start_lng = path_points[i]
        end_lat, end_lng = path_points[i + 1]
        start_h3 = h3.geo_to_h3(start_lat, start_lng, resolution)
        end_h3 = h3.geo_to_h3(end_lat, end_lng, resolution)
        try:
            segment_cells = list(h3.h3_line(start_h3, end_h3))
        except Exception:
            segment_cells = [start_h3, end_h3]

        for cell in segment_cells:
            if cell not in seen:
                seen.add(cell)
                cells.append(cell)

    return cells


DIFFICULTY_COLOR = {
    "easy": "#4CAF50",
    "moderate": "#2196F3",
    "hard": "#FF9800",
    "extreme": "#F44336",
}

colors = {
    "trail":        "#2196F3",
    "cafe":         "#FF9800",
    "restaurant":   "#E91E63",
    "shelter":      "#4CAF50",
    "viewpoint":    "#9C27B0",
    "water_source": "#00BCD4",
    "campsite":     "#795548",
    "active":       "#FFC107",
    "overdue":      "#F44336",
    "event":        "#673AB7",
}

features = []
seen_h3 = set()

# ── Trail route cells via geometry/h3_line at DISPLAY_RES ─────────────────────
for t in trails:
    path_points = read_trail_path_points(t)
    route_cells = compute_route_cells_from_points(path_points, DISPLAY_RES)

    trail_color = DIFFICULTY_COLOR.get(t["difficulty"], colors["trail"])
    for cell in route_cells:
        if cell not in seen_h3:
            features.append(h3_to_geojson_polygon(cell, {
                "name":  t["name"],
                "type":  "trail",
                "color": trail_color,
                "popup": f"🥾 <b>{t['name']}</b><br>Difficulty: {t['difficulty']}<br>H3 cell: {cell}"
            }))
            seen_h3.add(cell)

# ── POI cells — compute at DISPLAY_RES from coordinates ──────────────────────
for p in pois:
    cell = resolve_cell_for_display(
        h3_index=p.get("h3_index"),
        lat=p.get("latitude"),
        lng=p.get("longitude"),
    )
    if cell and cell not in seen_h3:
        features.append(h3_to_geojson_polygon(cell, {
            "name":  p["name"],
            "type":  p["category"],
            "color": colors.get(p["category"], "#999"),
            "popup": f"📍 <b>{p['name']}</b><br>Category: {p['category']}<br>H3 cell: {cell}"
        }))
        seen_h3.add(cell)

# ── Active / overdue check-in cells ──────────────────────────────────────────
for c in checkins:
    cell = resolve_cell_for_display(
        h3_index=c.get("h3_index"),
        lat=c.get("latitude"),
        lng=c.get("longitude"),
    )
    if cell and cell not in seen_h3:
        features.append(h3_to_geojson_polygon(cell, {
            "name":  c["username"],
            "type":  c["status"],
            "color": colors.get(c["status"], "#FFC107"),
            "popup": f"🆘 <b>{c['username']}</b><br>Status: {c['status']}<br>H3 cell: {cell}"
        }))
        seen_h3.add(cell)

geojson = {"type": "FeatureCollection", "features": features}

# ── Polyline routes: use stored geometry when available ────────────────────────
trail_routes = []
for t in trails:
    path_points = read_trail_path_points(t)
    path = [[lat, lng] for lat, lng in path_points]

    trail_routes.append({
        "start":      [t["start_lat"], t["start_lng"]],
        "end":        [t["end_lat"],   t["end_lng"]],
        "path":       path,
        "name":       t["name"],
        "difficulty": t["difficulty"],
        "color":      DIFFICULTY_COLOR.get(t["difficulty"], "#2196F3"),
    })

# ── Markers ────────────────────────────────────────────────────────────────────
poi_icons = {"cafe": "☕", "restaurant": "🍽️", "shelter": "🏠",
             "viewpoint": "👁️", "water_source": "💧", "campsite": "⛺"}

all_markers = (
    [{"lat": t["start_lat"], "lng": t["start_lng"], "name": t["name"],
      "icon": "🥾", "type": "trail"} for t in trails] +
    [{"lat": p["latitude"],  "lng": p["longitude"],  "name": p["name"],
      "icon": poi_icons.get(p["category"], "📍"), "type": p["category"]} for p in pois] +
    [{"lat": e["location_lat"], "lng": e["location_lng"], "name": e["title"],
      "icon": "🎪", "type": "event"} for e in events] +
    [{"lat": c["latitude"], "lng": c["longitude"],
      "name": f"{c['username']} ({c['status']})",
      "icon": "🔴" if c["status"] == "overdue" else "🟡",
      "type": c["status"]} for c in checkins]
)

html = f"""<!DOCTYPE html>
<html>
<head>
    <title>🏔️ MTSIS — H3 Map (res {DISPLAY_RES})</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ width: 100%; height: 100vh; }}
        .legend {{
            background: white; padding: 10px 14px; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.25); line-height: 26px; font: 13px/1.5 Arial;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 8px; }}
        .legend-color {{ width: 16px; height: 16px; border-radius: 3px; flex-shrink: 0; }}
    </style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map = L.map('map').setView([43.12, 76.98], 12);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);

// ── H3 hexagons (resolution {DISPLAY_RES}) ──────────────────────────────────
const geojson = {json.dumps(geojson)};
L.geoJSON(geojson, {{
    style: function(feature) {{
        return {{
            fillColor: feature.properties.color,
            weight: 2,
            opacity: 0.9,
            color: feature.properties.color,
            fillOpacity: 0.35
        }};
    }},
    onEachFeature: function(feature, layer) {{
        layer.bindPopup(feature.properties.popup);
        layer.on('mouseover', function(e) {{
            e.target.setStyle({{ fillOpacity: 0.6, weight: 3 }});
        }});
        layer.on('mouseout', function(e) {{
            e.target.setStyle({{ fillOpacity: 0.35, weight: 2 }});
        }});
    }}
}}).addTo(map);

// ── Trail route polylines (stored geometry, colored by difficulty) ───────────
const routes = {json.dumps(trail_routes)};
routes.forEach(r => {{
    const line = L.polyline(r.path, {{
        color: r.color,
        weight: 4,
        opacity: 0.85,
        dashArray: '12, 6'
    }}).addTo(map);
    line.bindPopup(
        '<b>🥾 ' + r.name + '</b><br>' +
        'Difficulty: <b>' + r.difficulty + '</b><br>' +
        '<small>Route geometry</small>'
    );

    // Start marker (circle)
    L.circleMarker(r.start, {{
        radius: 7, color: r.color, fillColor: r.color,
        fillOpacity: 1, weight: 2
    }}).addTo(map).bindPopup('<b>▶ Start:</b> ' + r.name);

    // End marker (square via divIcon)
    L.marker(r.end, {{
        icon: L.divIcon({{
            html: '<div style="width:12px;height:12px;background:' + r.color +
                  ';border:2px solid white;border-radius:2px;margin:-6px 0 0 -6px"></div>',
            className: '', iconSize: [12, 12]
        }})
    }}).addTo(map).bindPopup('<b>■ End:</b> ' + r.name);
}});

// ── POI / event / checkin markers ──────────────────────────────────────────
const markers = {json.dumps(all_markers)};
markers.forEach(m => {{
    const icon = L.divIcon({{
        html: '<div style="font-size:22px;text-align:center;line-height:1">' + m.icon + '</div>',
        iconSize: [28, 28], className: ''
    }});
    L.marker([m.lat, m.lng], {{ icon }}).addTo(map)
        .bindPopup('<b>' + m.icon + ' ' + m.name + '</b><br>Type: ' + m.type);
}});

// ── Legend ─────────────────────────────────────────────────────────────────
const legend = L.control({{ position: 'bottomright' }});
legend.onAdd = function() {{
    const div = L.DomUtil.create('div', 'legend');
    div.innerHTML =
        '<b>🏔️ MTSIS — H3 res {DISPLAY_RES}</b><br>' +
        '<i style="font-size:11px;color:#888">Hexagons ~{DISPLAY_HEX_AREA_KM2:.2f} km² each</i><br><br>' +
        '<b>Trails (by difficulty)</b><br>' +
        '<div class="legend-item"><div class="legend-color" style="background:#4CAF50"></div> Easy</div>' +
        '<div class="legend-item"><div class="legend-color" style="background:#2196F3"></div> Moderate</div>' +
        '<div class="legend-item"><div class="legend-color" style="background:#FF9800"></div> Hard</div>' +
        '<div class="legend-item"><div class="legend-color" style="background:#F44336"></div> Extreme</div>' +
        '<br><b>POIs</b><br>' +
        '<div class="legend-item"><div class="legend-color" style="background:#FF9800"></div> Cafe</div>' +
        '<div class="legend-item"><div class="legend-color" style="background:#E91E63"></div> Restaurant</div>' +
        '<div class="legend-item"><div class="legend-color" style="background:#4CAF50"></div> Shelter</div>' +
        '<br><b>Safety</b><br>' +
        '<div class="legend-item"><div class="legend-color" style="background:#FFC107"></div> Active check-in</div>' +
        '<div class="legend-item"><div class="legend-color" style="background:#F44336"></div> Overdue!</div>';
    return div;
}};
legend.addTo(map);
</script>
</body>
</html>"""

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h3_map.html")
with open(output_path, "w") as f:
    f.write(html)

print(f"Map saved to: {output_path}")
print(f"Display resolution: {DISPLAY_RES} (~{DISPLAY_HEX_AREA_KM2:.2f} km² per hexagon)")
webbrowser.open("file://" + output_path)
