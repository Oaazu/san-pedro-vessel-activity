"""
Helper for drawing zones.
Exports a sample of positions where ships were stopped (anchored or moored)
as a GeoJSON file you can open in geojson.io and draw polygons around.
"""
import json
import duckdb

pts = duckdb.sql("""
    SELECT LAT, LON, Status
    FROM 'commercial.parquet'
    WHERE SOG < 0.5 AND Status IN (1, 5)
    USING SAMPLE 4000 ROWS
""").fetchall()

features = [
    {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "status": "anchored" if status == 1 else "moored",
            "marker-color": "#E8913A" if status == 1 else "#3A9E6B",
            "marker-size": "small",
        },
    }
    for lat, lon, status in pts
]

with open("stopped_points.geojson", "w") as f:
    json.dump({"type": "FeatureCollection", "features": features}, f)

print(f"Saved {len(features)} points to stopped_points.geojson")
print("Open geojson.io -> Open -> File -> stopped_points.geojson, then draw zones around the clusters.")
