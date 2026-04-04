import glob
import pandas as pd
import duckdb
import os

DATA_DIR = "datalake/silver/telemetry"
print(f"Checking {DATA_DIR}...")

files = glob.glob(f"{DATA_DIR}/**/*.parquet", recursive=True)
print(f"Found {len(files)} parquet files.")

if not files:
    print("WARNING: No files found.")
    exit(1)

print(f"First file: {files[0]}")

print("\n--- Trying Pandas read_parquet on first file ---")
try:
    df_pd = pd.read_parquet(files[0])
    print("Success!")
    print(df_pd.head())
    print(df_pd.dtypes)
except Exception as e:
    print(f"Pandas Failed: {e}")

print("\n--- Trying DuckDB read_parquet with glob ---")
try:
    query_glob = f"SELECT count(*) as count FROM read_parquet('{DATA_DIR}/**/*.parquet')"
    print(f"Query: {query_glob}")
    res = duckdb.query(query_glob).fetchall()
    print(f"Result: {res}")
except Exception as e:
    print(f"DuckDB Glob Failed: {e}")

print("\n--- Trying DuckDB read_parquet with list ---")
try:
    # Explicit list
    files_str = "', '".join(files)
    query_list = f"SELECT count(*) as count FROM read_parquet(['{files_str}'])"
    res = duckdb.query(query_list).fetchall()
    print(f"Result: {res}")
except Exception as e:
    print(f"DuckDB List Failed: {e}")
