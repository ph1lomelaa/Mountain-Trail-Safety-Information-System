# Mountain Trail & Safety Information System (MTSIS)

Safety monitoring system for mountain hikers with H3 spatial indexing.

Muslima Kosmagambetova - 230103269
Altynai Nazik - 230103323

## How to Run

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Initialize the database

```bash
python init_db.py
```

### 3. (Optional) Import real trail data from OpenStreetMap

```bash
python scripts/import_almaty_osm.py
```

### 4. Start the server

```bash
uvicorn app.main:app --reload
```

API available at: http://127.0.0.1:8000
Interactive docs: http://127.0.0.1:8000/docs

### 5. (Optional) Open the frontend

Open `front-lite/index.html` in a browser.

---

## Roles

| Role | Description |
|------|-------------|
| `admin` | Full access |
| `ranger` | Monitors active hikers, can trigger overdue detection |
| `hiker` | Can check in/out on trails |

Switch roles via the `X-Demo-Role` header or the role selector in the frontend.

---

## How H3 is Used

- Every trail, POI, and check-in stores an `h3_index` column for spatial queries
- When a hiker checks in, the full route is encoded as H3 cells (resolution 9) in `safety_checkin_cells`
- `GET /h3/region/{resolution}/boundaries` aggregates trails, POIs, and active check-ins by H3 cell — used to color the map grid (red = active hikers)
- `GET /trails/{id}/h3-cells` returns H3 cells along a trail geometry for route visualization# Mountain-Trail-Safety-Information-System
