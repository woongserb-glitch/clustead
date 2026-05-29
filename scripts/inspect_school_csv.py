import csv


path = "data/school/school.csv"

encodings = [
    "utf-8-sig",
    "cp949",
    "euc-kr",
    "utf-8",
]

for encoding in encodings:
    try:
        with open(path, encoding=encoding, newline="") as file:
            reader = csv.DictReader(file)

            print(f"[SCHOOL] encoding: {encoding}")
            print(f"[SCHOOL] columns: {reader.fieldnames}")

            for index, row in enumerate(reader):
                print(f"[SCHOOL] sample {index + 1}: {row}")

                if index >= 2:
                    break

            break

    except UnicodeDecodeError:
        continue

    except FileNotFoundError:
        print(f"[SCHOOL ERROR] 파일 없음: {path}")
        break

    except Exception as e:
        print("[SCHOOL ERROR]", e)
        break