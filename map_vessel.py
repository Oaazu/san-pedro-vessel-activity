import duckdb
import folium
import pandas as pd

MMSI = 636021815  # DALIS - change this to map a different vessel

# Pull this vessel's positions in time order
df = duckdb.sql(f"""
    SELECT BaseDateTime, LAT, LON, SOG, Status, VesselName, VesselType
    FROM 'commercial.parquet'
    WHERE MMSI = {MMSI}
    ORDER BY BaseDateTime
""").df()

name = df["VesselName"].iloc[0]
print(f"{name} ({MMSI}): {len(df)} points | VesselType {df['VesselType'].iloc[0]}")
print(f"First seen: {df['BaseDateTime'].min()}  |  Last seen: {df['BaseDateTime'].max()}")
print("\nStatus counts (1 = at anchor, 5 = moored, 0 = underway):")
print(df["Status"].value_counts())

# ---------- Map ----------
colors = {0: "blue", 1: "orange", 5: "green"}
m = folium.Map(location=[df["LAT"].mean(), df["LON"].mean()], zoom_start=12)
folium.PolyLine(df[["LAT", "LON"]].values.tolist(), color="gray", weight=1).add_to(m)
for _, r in df.iloc[::20].iterrows():
    folium.CircleMarker(
        [r["LAT"], r["LON"]],
        radius=3,
        color=colors.get(r["Status"], "red"),
        fill=True,
        popup=f"{r['BaseDateTime']} | speed {r['SOG']} kn | status {r['Status']}",
    ).add_to(m)
m.save(f"vessel_{MMSI}.html")
print(f"\nMap saved to vessel_{MMSI}.html")

# ---------- Hours by status ----------
df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"])
gap_h = df["BaseDateTime"].diff().shift(-1).dt.total_seconds() / 3600
df["hours"] = gap_h.where(gap_h <= 1, 0)  # ignore gaps over 1 hour (signal loss / left area)

print("\nHours by status:")
print(df.groupby("Status")["hours"].sum().round(1))
print(f"Ignored gaps over 1 hour: {(gap_h > 1).sum()}")

# ---------- Raw segments (status changes) ----------
df["seg"] = (df["Status"] != df["Status"].shift()).cumsum()
segs = df.groupby("seg").agg(
    status=("Status", "first"),
    start=("BaseDateTime", "first"),
    end=("BaseDateTime", "last"),
    hours=("hours", "sum"),
)

# ---------- Clean timeline (drop blips, merge repeated statuses) ----------
s = segs[segs["hours"] > 0.5].copy()
s["grp"] = (s["status"] != s["status"].shift()).cumsum()
timeline = s.groupby("grp").agg(
    status=("status", "first"),
    start=("start", "first"),
    end=("end", "last"),
    hours=("hours", "sum"),
)
timeline["days"] = (timeline["hours"] / 24).round(1)
timeline["hours"] = timeline["hours"].round(1)

print("\nClean timeline:")
print(timeline.to_string())