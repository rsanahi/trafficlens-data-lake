import pandas as pd
import duckdb
import glob

print("--- DIAGNOSTIC START ---")

# 1. Check Silver Data
silver_files = glob.glob("datalake/silver/telemetry/**/*.parquet", recursive=True)
print(f"Silver Files found: {len(silver_files)}")

if not silver_files:
    print("CRITICAL: No Silver data found.")
    exit(1)

try:
    con = duckdb.connect()
    silver_df = con.execute(f"SELECT source_file, count(*) as cnt FROM read_parquet('datalake/silver/telemetry/**/*.parquet') GROUP BY source_file LIMIT 5").df()
    print("\nSilver source_file examples:")
    print(silver_df)
except Exception as e:
    print(f"Error reading Silver: {e}")

# 2. Check Gold Data
gold_file = "datalake/gold/dim_trips.parquet"
try:
    if not glob.glob(gold_file):
        print("\nCRITICAL: Gold file dim_trips.parquet NOT found.")
    else:
        gold_df = con.execute(f"SELECT trip_id, duration_seconds FROM read_parquet('{gold_file}') LIMIT 5").df()
        print("\nGold trip_id examples:")
        print(gold_df)
        
        # Check intersection
        if not silver_df.empty and not gold_df.empty:
             # Check if silver source_files represent a subset of gold trip_ids
             silver_files_set = set(silver_df['source_file'])
             gold_trips_set = set(gold_df['trip_id'])
             intersection = silver_files_set.intersection(gold_trips_set)
             print(f"\nIntersection count: {len(intersection)}")
             if len(intersection) == 0:
                 print("CRITICAL: Silver source_file does NOT match Gold trip_id. Filter will fail.")
                 print(f"Silver sample: {list(silver_files_set)[0]}")
                 print(f"Gold sample: {list(gold_trips_set)[0]}")
except Exception as e:
    print(f"Error reading Gold: {e}")

print("--- DIAGNOSTIC END ---")
