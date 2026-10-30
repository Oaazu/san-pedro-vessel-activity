"""
One-time fix: the anchorage and terminal names in zones.geojson were swapped.
Renames them based on the zone check (% anchored vs % moored).
Makes a backup first: zones_backup.geojson
"""
import json
import shutil

RENAME = {
    "anchorage1_san_pedro": "terminal_sp_A",
    "anchorage2_san_pedro": "terminal_sp_B",
    "anchorage3_long_beach": "terminal_lb_A",
    "terminal1_long_beach": "anchorage_lb_1",
    "terminal2_long_beach": "anchorage_lb_2",
    "terminal3_long_beach": "anchorage_lb_3",
    "terminal4_san_pedro": "anchorage_sp_1",
    "terminal_2_san_pedro": "anchorage_sp_2",
}

shutil.copy("zones.geojson", "zones_backup.geojson")
with open("zones.geojson", encoding="utf-8-sig") as f:
    gj = json.load(f)

changed = 0
for feat in gj["features"]:
    props = feat.get("properties") or {}
    old = props.get("name")
    if old in RENAME:
        props["name"] = RENAME[old]
        print(f"{old:24} -> {RENAME[old]}")
        changed += 1

with open("zones.geojson", "w", encoding="utf-8") as f:
    json.dump(gj, f)
print(f"\nRenamed {changed} zones. Backup saved as zones_backup.geojson")
