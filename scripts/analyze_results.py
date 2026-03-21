import json
import glob
import os
from collections import defaultdict

RESULTS_DIR = "results"


def safe_bool(value):
    """Normalize truthy values across possible JSONL formats."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {
            "true", "1", "yes", "ok", "valid", "success", "passed"
        }
    if isinstance(value, (int, float)):
        return value != 0
    return False


def get_first_present(record, keys, default=None):
    """Return the first matching key from a record."""
    for key in keys:
        if key in record:
            return record[key]
    return default


def normalize_model_name(raw_name, filename):
    """Infer model name from record or filename."""
    if raw_name:
        name = str(raw_name).strip()
        lower_name = name.lower()

        if "codellama" in lower_name:
            return "CodeLlama 7B"
        if "starcoder" in lower_name:
            return "StarCoder2 7B"
        if "1.3" in lower_name or "1p3" in lower_name:
            return "DeepSeek-Coder 1.3B"
        if "6.7" in lower_name or "6p7" in lower_name:
            return "DeepSeek-Coder 6.7B"
        if "deepseek" in lower_name:
            return "DeepSeek-Coder 6.7B"

        return name

    lower = filename.lower()

    if "codellama" in lower:
        return "CodeLlama 7B"
    if "starcoder" in lower:
        return "StarCoder2 7B"
    if "deepseek" in lower and ("1p3b" in lower or "1.3b" in lower):
        return "DeepSeek-Coder 1.3B"
    if "deepseek" in lower and ("6p7b" in lower or "6.7b" in lower):
        return "DeepSeek-Coder 6.7B"

    # Important fallback for your current filenames
    if "1p3b" in lower or "1.3b" in lower:
        return "DeepSeek-Coder 1.3B"
    if "6p7b" in lower or "6.7b" in lower:
        return "DeepSeek-Coder 6.7B"

    return "Unknown"


def normalize_repo_name(raw_name, filename):
    """Infer repository name from record or filename."""
    if raw_name:
        return str(raw_name)

    lower = filename.lower()

    if "commons_io" in lower:
        return "commons-io"
    if "commons_lang" in lower:
        return "commons-lang"
    if "guava" in lower:
        return "guava"
    if "commons_collections" in lower:
        return "commons-collections"

    return "unknown"


def is_valid_patch(record):
    """Determine whether a record represents a successful/valid patch."""
    candidates = [
        "patch_valid",
        "valid_patch",
        "is_valid",
        "success",
        "ok",
        "applied",
        "passed",
        "compile_success",
    ]
    value = get_first_present(record, candidates, None)
    return safe_bool(value)


def is_guardrail_failure(record):
    """Determine whether a record represents a guardrail / validation failure."""
    candidates = [
        "guardrail_failure",
        "guardrail_failed",
        "validation_failed",
        "patch_invalid",
        "failed_guardrail",
    ]
    value = get_first_present(record, candidates, None)

    if value is not None:
        return safe_bool(value)

    # Fallback: if patch is invalid, count it as a guardrail-style failure
    return not is_valid_patch(record)


def get_lines_added(record):
    return get_first_present(
        record,
        [
            "lines_added",
            "added_lines",
            "diff_added",
            "diff_add",
            "added",
            "insertions",
            "num_added_lines",
            "added_line_count",
        ],
        0,
    ) or 0


def get_lines_deleted(record):
    return get_first_present(
        record,
        [
            "lines_deleted",
            "deleted_lines",
            "diff_deleted",
            "diff_del",
            "deleted",
            "deletions",
            "num_deleted_lines",
            "deleted_line_count",
        ],
        0,
    ) or 0


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[WARN] Skipping malformed JSON line in {path}")
    return rows


def analyze_files():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.jsonl")))

    if not files:
        print("No JSONL files found in results/")
        return

    table2_agg = defaultdict(lambda: {
        "samples": 0,
        "success_count": 0,
        "lines_added_total": 0,
        "lines_deleted_total": 0
    })

    print("=" * 95)
    print("TABLE 1: Experiment Results Summary")
    print("=" * 95)
    print(
        f"{'Repository':<20} {'Samples':<8} {'Model':<24} {'Valid':<8} "
        f"{'Guardrail Failures':<18} {'Success Rate':<12}"
    )
    print("-" * 95)

    for path in files:
        filename = os.path.basename(path)
        rows = load_jsonl(path)

        if not rows:
            continue

        sample_count = len(rows)

        model_name = normalize_model_name(
            get_first_present(rows[0], ["model", "model_name", "llm_model"], None),
            filename
        )

        repo_name = normalize_repo_name(
            get_first_present(rows[0], ["repository", "repo", "repo_name", "projectName"], None),
            filename
        )

        valid_count = sum(1 for row in rows if is_valid_patch(row))
        guardrail_failures = sum(1 for row in rows if is_guardrail_failure(row))
        success_rate = (valid_count / sample_count) * 100 if sample_count else 0.0

        print(
            f"{repo_name:<20} {sample_count:<8} {model_name:<24} {valid_count:<8} "
            f"{guardrail_failures:<18} {success_rate:>8.1f}%"
        )

        # Aggregate for Table 2 by model
        table2_agg[model_name]["samples"] += sample_count
        table2_agg[model_name]["success_count"] += valid_count
        table2_agg[model_name]["lines_added_total"] += sum(float(get_lines_added(row)) for row in rows)
        table2_agg[model_name]["lines_deleted_total"] += sum(float(get_lines_deleted(row)) for row in rows)

    print()
    print("=" * 95)
    print("TABLE 2: Multi-Model Comparison")
    print("=" * 95)
    print(
        f"{'Model':<24} {'Samples':<8} {'Success Count':<14} "
        f"{'Avg Lines Added':<16} {'Avg Lines Deleted':<18}"
    )
    print("-" * 95)

    for model_name, stats in sorted(table2_agg.items()):
        samples = stats["samples"]
        success_count = stats["success_count"]
        avg_added = stats["lines_added_total"] / samples if samples else 0.0
        avg_deleted = stats["lines_deleted_total"] / samples if samples else 0.0

        print(
            f"{model_name:<24} {samples:<8} {success_count:<14} "
            f"{avg_added:<16.2f} {avg_deleted:<18.2f}"
        )

    print()
    print("=" * 95)
    print("Done. Use this output to populate the paper tables and README summary.")
    print("=" * 95)


if __name__ == "__main__":
    analyze_files()