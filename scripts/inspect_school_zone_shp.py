import geopandas as gpd


path = "data/school/zone/초등학교통학구역.shp"

gdf = gpd.read_file(path)

print("[ROW COUNT]", len(gdf))

print("\n[COLUMNS]")
print(gdf.columns.tolist())

print("\n[FIRST ROW]")
print(gdf.iloc[0])

print("\n[CRS]")
print(gdf.crs)

print("\n[GEOMETRY TYPE]")
print(gdf.geometry.iloc[0].geom_type)