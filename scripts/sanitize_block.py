#!/usr/bin/env python3
import argparse

def extract_first_brace_block(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No '{' found in LLM output")

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1]

    raise ValueError("Unbalanced braces: could not find matching '}'")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    raw = open(args.inp, "r", encoding="utf-8", errors="replace").read()
    block = extract_first_brace_block(raw).strip() + "\n"
    open(args.out, "w", encoding="utf-8").write(block)
    print("Wrote sanitized block:", args.out)

if __name__ == "__main__":
    main()
