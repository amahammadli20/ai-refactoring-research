#!/usr/bin/env python3
import argparse
import json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods-json", required=True)
    ap.add_argument("--index", type=int, required=True, help="Index into methods[] array")
    ap.add_argument("--new-body-file", required=True, help="Path to a file containing new method block text (including braces)")
    ap.add_argument("--in-place", action="store_true", help="Modify the original file")
    ap.add_argument("--out-file", default=None, help="Write modified file to this path instead of in-place")
    args = ap.parse_args()

    p = json.load(open(args.methods_json, "r", encoding="utf-8"))
    m = p["methods"][args.index]
    fp = m["file"]

    start_b = m["start_byte"]
    end_b = m["end_byte"]

    src = open(fp, "rb").read()
    new_block = open(args.new_body_file, "rb").read()

    # Replace ONLY the method/constructor node span
    out = src[:start_b] + new_block + src[end_b:]

    if args.in_place:
        open(fp, "wb").write(out)
        print("Wrote in-place:", fp)
    else:
        if not args.out_file:
            raise SystemExit("--out-file is required unless --in-place")
        open(args.out_file, "wb").write(out)
        print("Wrote:", args.out_file)

if __name__ == "__main__":
    main()