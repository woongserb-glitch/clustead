import json
from pathlib import Path


path = Path("data/school/school_zone.json")

if not path.exists():
    print(f"[ERROR] 파일 없음: {path}")
    exit()

with open(path, encoding="utf-8-sig") as file:
    data = json.load(file)

print("[TYPE]", type(data))

if isinstance(data, dict):
    print("[TOP KEYS]", list(data.keys()))

    for key, value in data.items():
        print(f"[KEY] {key} / type={type(value)}")

        if isinstance(value, list):
            print(f"[LIST COUNT] {len(value)}")

            if value:
                print("[FIRST ITEM TYPE]", type(value[0]))

                if isinstance(value[0], dict):
                    print("[FIRST ITEM KEYS]", list(value[0].keys()))
                    print("[FIRST ITEM SAMPLE]", value[0])

            break

elif isinstance(data, list):
    print("[LIST COUNT]", len(data))

    if data:
        print("[FIRST ITEM TYPE]", type(data[0]))

        if isinstance(data[0], dict):
            print("[FIRST ITEM KEYS]", list(data[0].keys()))
            print("[FIRST ITEM SAMPLE]", data[0])


records = data.get("records", [])

print("[RECORD COUNT]", len(records))

if records:
    first = records[0]

    print("[FIRST RECORD TYPE]", type(first))

    if isinstance(first, dict):
        print("[FIRST RECORD KEYS]")
        print(list(first.keys()))

        print("\n[FIRST RECORD SAMPLE]")
        print(first)