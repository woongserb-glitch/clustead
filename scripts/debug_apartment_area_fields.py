from services.preload_service import (
    load_apartment_data,
    apartment_data,
)

TARGET = "마포래미안푸르지오"

load_apartment_data()

for apt in apartment_data:
    if TARGET in apt.get("name", ""):
        print("[TARGET]", apt.get("name"))
        print("household_count:", apt.get("household_count"))
        print("parking_count:", apt.get("parking_count"))
        print("approval_date:", apt.get("approval_date"))
        print("builder:", apt.get("builder"))
        print("area_under_60:", apt.get("area_under_60"))
        print("area_60_85:", apt.get("area_60_85"))
        print("area_85_135:", apt.get("area_85_135"))
        print("area_over_135:", apt.get("area_over_135"))
        print()
        print("[FULL APT KEYS]")
        print(apt.keys())
        break