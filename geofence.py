"""
Geofencing: labels every ship position with the zone it was in
(anchorage, terminal, or outside) and rebuilds each visit as a
zone-by-zone sequence, e.g. anchorage_main -> terminal_A -> anchorage_main -> terminal_B.

Needs: zones.geojson (polygons, each with a "name" property) and commercial.parquet
Install once: pip install shapely
"""
import json
import duckdb
import pandas as pd
import shapely
from shapely.geometry import shape

GAP_IGNORE_H = 1      # gaps longer than this don't count as time in a zone
NEW_VISIT_H = 12      # a gap longer than this starts a new visit
MIN_STAY_H = 0.5      # stays shorter than this are dropped (passing through / flicker)
FOCUS_MMSI = 636021815  # DALIS - the vessel whose route is printed at the end

# ---------- 1. Load zones ----------
with open("zones.geojson") as f:
    gj = json.load(f)
zones = []
for i, feat in enumerate(gj["features"]):
    geom = shape(feat["geometry"])
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        continue
    name = (feat.get("properties") or {}).get("name") or f"zone_{i + 1}"
    zones.append((name, geom))
print(f"Loaded {len(zones)} zones: {', '.join(n for n, _ in zones)}")

# ---------- 2. Load positions ----------
df = duckdb.sql("""
    SELECT MMSI, BaseDateTime, LAT, LON, SOG, Status, VesselName, VesselType
    FROM 'commercial.parquet'
    ORDER BY MMSI, BaseDateTime
""").df()
df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"])
print(f"Loaded {len(df):,} positions for {df['MMSI'].nunique()} vessels")

# ---------- 3. Label each position with its zone ----------
df["zone"] = "outside"
lon, lat = df["LON"].to_numpy(), df["LAT"].to_numpy()
for name, geom in zones:
    inside = shapely.contains_xy(geom, lon, lat)
    df.loc[inside & (df["zone"] == "outside"), "zone"] = name  # first matching zone wins
counts = df["zone"].value_counts()
print("\nPositions per zone:")
print(counts.to_string())

# ---------- 4. Time per point and visits (same rules as build_events.py) ----------
g = df.groupby("MMSI")["BaseDateTime"]
gap_next = (g.shift(-1) - df["BaseDateTime"]).dt.total_seconds() / 3600
gap_prev = (df["BaseDateTime"] - g.shift(1)).dt.total_seconds() / 3600
df["hours"] = gap_next.where(gap_next <= GAP_IGNORE_H, 0).fillna(0)
new_vessel = df["MMSI"] != df["MMSI"].shift()
df["visit"] = ((gap_prev > NEW_VISIT_H) | new_vessel).groupby(df["MMSI"]).cumsum()

# ---------- 5. Zone segments, then clean stays ----------
change = (df["zone"] != df["zone"].shift()) | new_vessel | (df["visit"] != df["visit"].shift())
df["seg"] = change.cumsum()
segs = df.groupby("seg").agg(
    MMSI=("MMSI", "first"), visit=("visit", "first"), zone=("zone", "first"),
    start=("BaseDateTime", "first"), end=("BaseDateTime", "last"), hours=("hours", "sum"),
    avg_speed=("SOG", "mean"),
)
s = segs[(segs["hours"] > MIN_STAY_H) & (segs["zone"] != "outside")].copy()
key = (s["zone"] != s["zone"].shift()) | (s["MMSI"] != s["MMSI"].shift()) | (s["visit"] != s["visit"].shift())
s["grp"] = key.cumsum()
stays = s.groupby("grp").agg(
    MMSI=("MMSI", "first"), visit=("visit", "first"), zone=("zone", "first"),
    start=("start", "first"), end=("end", "last"), hours=("hours", "sum"),
).reset_index(drop=True)

info = df.groupby("MMSI").agg(name=("VesselName", "first"), vessel_type=("VesselType", "first"))
info["type_group"] = pd.cut(info["vessel_type"], bins=[69, 79, 89], labels=["cargo", "tanker"])
stays = stays.merge(info, on="MMSI")
stays["days"] = (stays["hours"] / 24).round(1)
stays["hours"] = stays["hours"].round(1)
duckdb.sql("COPY stays TO 'zone_stays.parquet' (FORMAT PARQUET)")
print(f"\nBuilt {len(stays):,} zone stays -> zone_stays.parquet")

# ---------- 6. Results ----------
summary = stays.groupby("zone").agg(
    vessels=("MMSI", "nunique"),
    stays=("MMSI", "size"),
    median_hours=("hours", "median"),
    total_days=("days", "sum"),
).sort_values("stays", ascending=False)
print("\nActivity by zone:")
print(summary.round(1).to_string())

route = (stays.groupby(["MMSI", "visit"])["zone"]
              .apply(lambda z: " -> ".join(z)).rename("route").reset_index())
print("\nMost common routes:")
print(route["route"].value_counts().head(10).to_string())

focus = stays[stays["MMSI"] == FOCUS_MMSI]
if len(focus):
    print(f"\nRoute for {focus['name'].iloc[0]}:")
    print(focus[["zone", "start", "end", "days"]].to_string(index=False))


print("\nZone check (% of points by crew status):")
print(duckdb.sql("""
    SELECT zone,
           ROUND(100 * AVG(CASE WHEN Status = 1 THEN 1 ELSE 0 END)) AS pct_anchored,
           ROUND(100 * AVG(CASE WHEN Status = 5 THEN 1 ELSE 0 END)) AS pct_moored,
           COUNT(*) AS points
    FROM df GROUP BY zone ORDER BY zone
"""))
