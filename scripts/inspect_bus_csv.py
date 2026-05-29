import pandas as pd

CSV_PATH = "data/bus/seoul_bus_stops.csv"

encodings = [
    "utf-8-sig",
    "cp949",
]

for enc in encodings:
    try:
        df = pd.read_csv(CSV_PATH, encoding=enc)

        print("[ENCODING]", enc)
        print("[COLUMNS]")
        print(df.columns.tolist())

        print()

        print("[SAMPLE]")
        print(df.iloc[0].to_dict())

        break

    except Exception as e:
        print(enc, e)