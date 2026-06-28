from apply_mpe_add_1_consistency_fixes import make_mapping_csvs, run_audit


if __name__ == "__main__":
    make_mapping_csvs()
    result = run_audit("manual", write=True)
    print("MPE Add 1 consistency audit complete")
    print(result)
