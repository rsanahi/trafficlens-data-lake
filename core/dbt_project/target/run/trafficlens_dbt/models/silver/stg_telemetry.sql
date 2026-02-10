
      create or replace view "trafficlens"."main"."stg_telemetry__dbt_int" as (
        select * from read_parquet('/Users/anahiruiz/Documents/GitHub/trafficlens-data-lake/datalake/silver/telemetry.parquet', union_by_name=False)
        -- if relation is empty, filter by all columns having null values
        
      );
    