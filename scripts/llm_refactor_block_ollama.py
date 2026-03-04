#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

PROMPT_TEMPLATE = """You are a code refactoring assistant.

OUTPUT FORMAT (MUST FOLLOW):
- Output ONLY the Java method body block.
- The output must be a single block that starts with '{{' and ends with '}}'.
- No markdown fences. No backticks. No explanations.

If you cannot comply exactly, output exactly:
{{}}

Refactor goals:
- Preserve behavior exactly.
- Improve readability.
- Reduce duplication where safe.
- Keep assertions and test intent unchanged.

Method body:
{body}
"""

def strip_code_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        lines = lines[1:]  # drop ``` or ```java
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return s

def extract_first_brace_block(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None

def is_block(text: str) -> bool:
    s = text.strip()
    return s.startswith("{") and s.endswith("}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-coder:6.7b")
    ap.add_argument("--in-block", required=True)
    ap.add_argument("--out-block", required=True)
    ap.add_argument("--retries", type=int, default=4)
    args = ap.parse_args()

    body = Path(args.in_block).read_text(encoding="utf-8", errors="replace")
    prompt = PROMPT_TEMPLATE.format(body=body)

    last_raw = ""
    for attempt in range(1, args.retries + 1):
        proc = subprocess.run(
            ["ollama", "run", args.model],
            input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out_raw = proc.stdout.decode("utf-8", errors="replace")
        last_raw = out_raw

        cleaned = strip_code_fences(out_raw)

        # First try: direct block
        if is_block(cleaned):
            Path(args.out_block).write_text(cleaned.strip() + "\n", encoding="utf-8")
            print(f"OK: wrote {args.out_block} (attempt {attempt})")
            return

        # Second try: extract first {...} block from anywhere in output
        blk = extract_first_brace_block(cleaned)
        if blk and is_block(blk):
            Path(args.out_block).write_text(blk.strip() + "\n", encoding="utf-8")
            print(f"OK: extracted block and wrote {args.out_block} (attempt {attempt})")
            return

        prompt = (
            "REMINDER: Output ONLY the Java method body block, starting with '{' and ending with '}'. "
            "No prose, no markdown.\n\n"
            + prompt
        )

    Path(args.out_block).write_text("{}", encoding="utf-8")
    print("WARN: model did not produce an extractable block; wrote {} to:", args.out_block, file=sys.stderr)
    print("Last model output (first 200 chars):", last_raw[:200].replace("\n", "\\n"), file=sys.stderr)
    sys.exit(2)

if __name__ == "__main__":
    main()
