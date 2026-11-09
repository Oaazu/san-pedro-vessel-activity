"""
Presentation map: all zones plus one vessel's route, numbered stop by stop.
Run after geofence.py. Output: route_map.html (open in any browser).
"""
import json
import duckdb
import folium
import pandas as pd

MMSI = 636021815  # DALIS

# ---------- Data ----------
with open("zones.geojson", encoding="utf-8-sig") as f:
    gj = json.load(f)
zones = [ft for ft in gj["features"]
         if ft["geometry"]["type"] in ("Polygon", "MultiPolygon")
         and (ft.get("properties") or {}).get("name", "").startswith(("anchorage", "terminal"))]

track = duckdb.sql(f"""
    SELECT BaseDateTime, LAT, LON FROM 'commercial.parquet'
    WHERE MMSI = {MMSI} ORDER BY BaseDateTime
""").df()
track["BaseDateTime"] = pd.to_datetime(track["BaseDateTime"])

stays = duckdb.sql(f"""
    SELECT * FROM 'zone_stays.parquet' WHERE MMSI = {MMSI} ORDER BY start
""").df()
name = stays["name"].iloc[0] if len(stays) else str(MMSI)

# ---------- Map ----------
# Esri basemap: free, no API key, and works when the HTML is opened as a local file
# (OpenStreetMap blocks map tiles requested from local files)
TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
# For a satellite view of the actual terminals, use World_Imagery instead:
# TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
m = folium.Map(location=[track["LAT"].mean(), track["LON"].mean()],
               zoom_start=12, tiles=TILES, attr="Tiles &copy; Esri")

for ft in zones:
    zname = ft["properties"]["name"]
    color = "#E8913A" if zname.startswith("anchorage") else "#2E8B57"
    folium.GeoJson(
        ft,
        style_function=lambda _, c=color: {"color": c, "weight": 2, "fillColor": c, "fillOpacity": 0.15},
        tooltip=zname,
    ).add_to(m)

folium.PolyLine(track[["LAT", "LON"]].values.tolist(), color="#1F4E79", weight=2, opacity=0.7).add_to(m)

for i, s in enumerate(stays.itertuples(), start=1):
    pts = track[(track["BaseDateTime"] >= s.start) & (track["BaseDateTime"] <= s.end)]
    if pts.empty:
        continue
    lat, lon = pts["LAT"].median(), pts["LON"].median()
    is_terminal = s.zone.startswith("terminal")
    color = "#2E8B57" if is_terminal else "#E8913A"
    folium.Marker(
        [lat, lon],
        icon=folium.DivIcon(html=f"""
            <div style="background:{color};color:white;border-radius:50%;width:26px;height:26px;
                        display:flex;align-items:center;justify-content:center;
                        font:bold 13px Arial;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.4);">{i}</div>"""),
        tooltip=f"{i}. {s.zone}: {s.days} days",
        popup=folium.Popup(f"<b>Stop {i}: {s.zone}</b><br>{s.start:%b %d %H:%M} to {s.end:%b %d %H:%M}<br>{s.days} days", max_width=260),
    ).add_to(m)

rows = "".join(
    f"<tr><td style='padding:2px 6px'><b>{i}</b></td><td style='padding:2px 6px'>{s.zone}</td>"
    f"<td style='padding:2px 6px;text-align:right'>{s.days} d</td></tr>"
    for i, s in enumerate(stays.itertuples(), start=1)
)
panel = f"""
<div style="position:fixed;top:12px;left:56px;z-index:9999;background:white;padding:10px 14px;
            border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);font:13px Arial;">
  <div style="font-size:15px;font-weight:bold;margin-bottom:4px;">{name}: port visit route</div>
  <div style="color:#555;margin-bottom:6px;">
    <span style="color:#E8913A;">&#9632;</span> Anchorage &nbsp;
    <span style="color:#2E8B57;">&#9632;</span> Terminal area &nbsp;
    <span style="color:#1F4E79;">&#9472;</span> Track
  </div>
  <table>{rows}</table>
</div>"""
m.get_root().html.add_child(folium.Element(panel))

m.save("route_map.html")
print(f"Saved route_map.html for {name} ({len(stays)} stops)")
