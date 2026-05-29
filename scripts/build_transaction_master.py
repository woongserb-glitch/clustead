from build_molit_transaction_master import build_master


if __name__ == "__main__":
    print("[INFO] build_transaction_master.py now delegates to the MOLIT transaction parser.")
    print("[INFO] Seoul Open Data transaction raw files are no longer used by the default transaction pipeline.")
    build_master()
