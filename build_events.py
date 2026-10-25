"""
Phase 1 - Metrics layer
Turns raw AIS positions for all commercial vessels into:
  events.parquet  -> one row per clean phase (underway / anchored / moored) per vessel visit
  visits.parquet  -> one row per vessel visit, with wait and berth metrics
"""
import duckdb
import pandas as pd

GAP_IGNORE_H = 1      # gaps longer than this don't count as time in a status
NEW_VISIT_H = 12      # a gap longer than this means the vessel left and came back
MIN_PHASE_H = 0.5     # phases shorter than this are treated as flicker and dropped

STATUS = {0: "underway", 1: "anchored", 4: "draught_constrained", 5: "moored"}

# ---------- 1. Load ----------
df = duckdb.sql("""
    SELECT MMSI, BaseDateTime, Status, VesselName, VesselType
    FROM 'commercial.parquet'
    ORDER BY MMSI, BaseDateTime
""").df()
df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"])
data_start, data_end = df["BaseDateTime"].min(), df["BaseDateTime"].max()
print(f"Loaded {len(df):,} rows for {df['MMSI'].nunique()} vessels")

# ---------- 2. Time between points (within each vessel) ----------
g = df.groupby("MMSI")["BaseDateTime"]
gap_next = (g.shift(-1) - df["BaseDateTime"]).dt.total_seconds() / 3600
gap_prev = (df["BaseDateTime"] - g.shift(1)).dt.total_seconds() / 3600
df["hours"] = gap_next.where(gap_next <= GAP_IGNORE_H, 0).fillna(0)

# ---------- 3. Split each vessel's data into visits ----------
new_vessel = df["MMSI"] != df["MMSI"].shift()
df["visit"] = ((gap_prev > NEW_VISIT_H) | new_vessel).groupby(df["MMSI"]).cumsum()

# ---------- 4. Raw segments: consecutive points with the same status ----------
change = (df["Status"] != df["Status"].shift()) | new_vessel | (df["visit"] != df["visit"].shift())
df["seg"] = change.cumsum()
segs = df.groupby("seg").agg(
    MMSI=("MMSI", "first"), visit=("visit", "first"), status=("Status", "first"),
    start=("BaseDateTime", "first"), end=("BaseDateTime", "last"), hours=("hours", "sum"),
)

# ---------- 5. Clean events: drop flicker, merge repeated statuses ----------
s = segs[segs["hours"] > MIN_PHASE_H].copy()
key_change = (s["status"] != s["status"].shift()) | (s["MMSI"] != s["MMSI"].shift()) | (s["visit"] != s["visit"].shift())
s["grp"] = key_change.cumsum()
events = s.groupby("grp").agg(
    MMSI=("MMSI", "first"), visit=("visit", "first"), status=("status", "first"),
    start=("start", "first"), end=("end", "last"), hours=("hours", "sum"),
).reset_index(drop=True)
events["status_label"] = events["status"].map(STATUS).fillna("other")

info = df.groupby("MMSI").agg(name=("VesselName", "first"), vessel_type=("VesselType", "first"))
info["type_group"] = pd.cut(info["vessel_type"], bins=[69, 79, 89], labels=["cargo", "tanker"])
events = events.merge(info, on="MMSI")
duckdb.sql("COPY events TO 'events.parquet' (FORMAT PARQUET)")
print(f"Built {len(events):,} events")

# ---------- 6. Visit metrics ----------
keys = ["MMSI", "visit"]
first_berth = events[events["status"] == 5].groupby(keys)["start"].min().rename("first_berth")
ev = events.merge(first_berth, on=keys, how="left")

anchored = ev["status"] == 1
visits = ev.groupby(keys).agg(
    name=("name", "first"), type_group=("type_group", "first"),
    visit_start=("start", "min"), visit_end=("end", "max"),
    first_berth=("first_berth", "first"),
)
visits["wait_before_berth_h"] = ev[anchored & (ev["start"] < ev["first_berth"])].groupby(keys)["hours"].sum()
visits["total_anchor_h"] = ev[anchored].groupby(keys)["hours"].sum()
visits["berth_h"] = ev[ev["status"] == 5].groupby(keys)["hours"].sum()
visits["berth_stops"] = ev[ev["status"] == 5].groupby(keys).size()
visits = visits.fillna({"wait_before_berth_h": 0, "total_anchor_h": 0, "berth_h": 0, "berth_stops": 0})
visits["berth_stops"] = visits["berth_stops"].astype(int)
visits[["wait_before_berth_h", "total_anchor_h", "berth_h"]] = visits[["wait_before_berth_h", "total_anchor_h", "berth_h"]].round(1)

# Visits cut off by the edges of the data window (their true wait may be longer)
edge = pd.Timedelta(hours=NEW_VISIT_H)
visits["cut_off"] = (visits["visit_start"] < data_start + edge) | (visits["visit_end"] > data_end - edge)
visits["wait_before_berth_days"] = (visits["wait_before_berth_h"] / 24).round(1)
visits = visits.reset_index()
duckdb.sql("COPY visits TO 'visits.parquet' (FORMAT PARQUET)")

berthed = visits[visits["berth_stops"] > 0]
print(f"Built {len(visits):,} visits | {len(berthed):,} reached a berth | {visits['cut_off'].sum()} cut off by the data window")

# ---------- 7. First look at the results ----------
full = berthed[~berthed["cut_off"]]
print("\nWait before first berth, in days (complete visits that berthed):")
print(full.groupby("type_group", observed=True)["wait_before_berth_h"]
          .describe(percentiles=[0.5])[["count", "mean", "50%", "max"]]
          .div([1, 24, 24, 24]).round(1)
          .rename(columns={"50%": "median"}))

print("\nTop 10 longest waits before first berth:")
cols = ["name", "type_group", "visit_start", "wait_before_berth_days", "berth_stops"]
print(full.nlargest(10, "wait_before_berth_h")[cols].to_string(index=False))
