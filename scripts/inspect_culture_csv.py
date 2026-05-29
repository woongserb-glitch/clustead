from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_PATH = BASE_DIR / "data" / "culture" / "culture_raw.csv"


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            df = pd.read_csv(path, encoding=enc)
            print(f"[CULTURE INSPECT] encoding={enc}")
            return df
        except Exception:
            continue
    raise RuntimeError(f"CSV 인코딩을 읽을 수 없습니다: {path}")


def main():
    df = read_csv_with_fallback(RAW_PATH)

    print(f"[CULTURE INSPECT] rows={len(df):,}, columns={len(df.columns)}")
    print("[CULTURE INSPECT] columns:")
    for col in df.columns:
        print(f"- {col}")

    for col in ["예약구분", "대분류명", "소분류명", "서비스상태"]:
        if col in df.columns:
            print(f"\n[CULTURE INSPECT] {col} value counts")
            print(df[col].value_counts(dropna=False).head(50).to_string())

    if "장소X좌표" in df.columns and "장소Y좌표" in df.columns:
        x = pd.to_numeric(df["장소X좌표"], errors="coerce")
        y = pd.to_numeric(df["장소Y좌표"], errors="coerce")
        valid = df[x.notna() & y.notna()]
        print(f"\n[CULTURE INSPECT] coordinate rows={len(valid):,} / {len(df):,}")

    sample_cols = [
        col for col in [
            "지역명", "예약구분", "대분류명", "소분류명", "서비스상태",
            "서비스명", "장소명", "장소X좌표", "장소Y좌표", "바로가기URL"
        ]
        if col in df.columns
    ]
    print("\n[CULTURE INSPECT] sample")
    print(df[sample_cols].head(20).to_string())


if __name__ == "__main__":
    main()
