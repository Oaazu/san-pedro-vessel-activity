import duckdb

duckdb.sql("""
    COPY (
        SELECT * FROM 'AIS_File_01.csv'
        WHERE VesselType BETWEEN 70 AND 89
    ) TO 'commercial.parquet' (FORMAT PARQUET)
""")
print(duckdb.sql("SELECT COUNT(*) AS rows, COUNT(DISTINCT MMSI) AS vessels FROM 'commercial.parquet'"))

print(duckdb.sql("""
    SELECT MMSI, ANY_VALUE(VesselName) AS name, COUNT(*) AS points
    FROM 'commercial.parquet'
    GROUP BY MMSI
    HAVING COUNT(*) FILTER (WHERE Status = 1) > 0
       AND COUNT(*) FILTER (WHERE Status = 5) > 0
    ORDER BY points DESC LIMIT 10
"""))

