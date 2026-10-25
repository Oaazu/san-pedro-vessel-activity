#import pandas as pd

#df = pd.read_csv("AIS_File_01.csv", nrows=1000)  # first 1,000 rows only
#print(df.columns.tolist())
#print(df.head())
import duckdb
f = "'AIS_File_01.csv'"

print(duckdb.sql(f"SELECT MIN(BaseDateTime) AS start, MAX(BaseDateTime) AS finish, COUNT(*) AS rows, COUNT(DISTINCT MMSI) AS vessels FROM {f}"))
print(duckdb.sql(f"SELECT TransceiverClass, COUNT(*) AS rows, COUNT(DISTINCT MMSI) AS vessels FROM {f} GROUP BY 1"))
print(duckdb.sql(f"SELECT VesselType, COUNT(DISTINCT MMSI) AS vessels FROM {f} GROUP BY 1 ORDER BY 2 DESC LIMIT 15"))