import geopandas as gpd

path = "data/school/zone/초등학교통학구역.shp"

gdf = gpd.read_file(path)

print(
    gdf[
        ["HAKGUDO_GB", "HAKGUDO_NM"]
    ].drop_duplicates().sort_values("HAKGUDO_GB")
)