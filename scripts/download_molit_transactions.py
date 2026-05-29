from transaction_layer_utils import MOLIT_TRANSACTION_RAW_DIR, ensure_transaction_dirs


MOLIT_SOURCE_URL = "https://rt.molit.go.kr/pt/xls/xls.do?mobileAt="


def main():
    ensure_transaction_dirs()
    print("[INFO] MOLIT automatic download is not enabled in this first-stage pipeline.")
    print("[INFO] Use the official MOLIT real transaction data page:")
    print(f"       {MOLIT_SOURCE_URL}")
    print("[INFO] Download apartment trade/rent files manually for Seoul, max one year per file.")
    print(f"[INFO] Put files in: {MOLIT_TRANSACTION_RAW_DIR}")
    print("[INFO] Recommended filenames:")
    print("       trade_2024.xlsx, trade_2025.xlsx, trade_2026.xlsx")
    print("       rent_2024.xlsx, rent_2025.xlsx, rent_2026.xlsx")
    print("[INFO] Then run: python scripts/build_molit_transaction_master.py")


if __name__ == "__main__":
    main()
