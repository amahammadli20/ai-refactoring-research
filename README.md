# AI-Driven Refactoring Research  
## A Modular Repository-Level Evaluation Infrastructure for LLM-Based Refactoring

---

# 1. Project Overview

This repository contains a modular research infrastructure for evaluating AI-driven automated refactoring at the repository level using local Large Language Models (LLMs).

The goal of this project is not simply to generate refactored code, but to build a reproducible experimental pipeline that enables systematic evaluation of LLM-based refactoring systems.

The system integrates:

- Repository-aware AST extraction
- Structural Java code summarization
- Local LLM-based refactoring
- Unified diff generation
- Automated patch validation
- SWE-style offline evaluation logging

This repository is structured as a modular monorepo to support incremental research expansion.

---

# 2. Research Motivation

Large Language Models can produce refactorings, but several key research questions remain:

- Are the generated refactorings syntactically valid?
- Are they diff-stable?
- Do they preserve structural properties?
- Can they be evaluated systematically?
- How reliable are local LLMs for repository-level tasks?

Most LLM refactoring experiments rely on manual inspection and lack automated validation.

This project builds the missing infrastructure required for:

- Repository-aware experimentation
- Diff-level validation
- Structured logging
- Quantitative structural comparison
- SWE-style benchmark evaluation

---

# 3. High-Level Architecture

The system follows the pipeline below:

Repository  
↓  
AST Extraction (Tree-sitter)  
↓  
Structural Summary Extraction  
↓  
Local LLM Refactoring  
↓  
Unified Diff Extraction  
↓  
Patch Sanitization  
↓  
git apply --check Validation  
↓  
Experiment Logging (JSONL)  

Each stage is modular and independently extensible.

---

# 4. Repository Structure

    ai-refactoring-research/

    modules/
      ast-extractor/

    scripts/
      local_llm.py
      run_swe_refactor_offline.py

    datasets/
      SWE-Refactor/

The repository is organized to allow additional modules (e.g., evaluation, benchmarking, structural comparison) to be added without restructuring the codebase.

---

# 5. Module 1 – AST Extraction (Tree-Sitter)

## Current Status: Skeleton + End-to-End Pipeline

The AST extractor module provides a repository-aware pipeline capable of:

- Cloning or reading a GitHub repository
- Scanning Java files
- Generating AST-like structured records
- Exporting JSONL outputs

Tree-sitter parsing is currently integrated at a structural level, but deeper semantic analysis is still under active development.

## Example Usage

    ast-extract \
      --repo https://github.com/apache/commons-io \
      --out out.jsonl \
      --languages java \
      --max-files 10 \
      --summary

Each processed file produces a JSONL record containing structural metadata and optional summaries.

---

# 6. Module 2 – Structural Java Summary

This module extracts quantitative structural metrics from Java source code to support before/after comparison.

Extracted metrics include:

- Total AST node count
- Named node count
- Maximum tree depth
- Class count
- Interface count
- Method count
- Constructor count
- Field count
- Local variable count
- Annotation count
- Control-flow statement count
- Node type histogram

This enables structural impact analysis of LLM-generated refactorings.

---

# 7. Module 3 – Local LLM Integration

## Design Principle

The system is designed to run fully offline without paid APIs.

## Tooling

- Ollama (local LLM runtime)
- deepseek-coder (1.3B and 6.7B variants tested)

## Installation

    brew install ollama
    ollama pull deepseek-coder:6.7b

This ensures reproducibility and controlled experimental conditions.

---

# 8. Module 4 – LLM Refactoring Engine

Implemented in:

    scripts/local_llm.py

## Capabilities

- Mode: code (returns full refactored file)
- Mode: diff (returns unified git patch)
- Snippet window control
- Head / tail / center selection
- Retry mechanism
- Markdown fence stripping
- Unified diff extraction
- Patch sanitization
- Hunk verification
- git apply --check validation
- Structured JSON experiment output

This module transforms raw model output into machine-applicable, validated patches.

---

# 9. Diff Validation Strategy

LLMs often generate:

- Commentary text
- Markdown formatting
- Malformed patch structures
- Incomplete hunks

To ensure patch reliability, the system:

1. Extracts raw model output
2. Removes markdown fences
3. Extracts content starting from `diff --git`
4. Sanitizes invalid lines
5. Verifies hunk format
6. Executes:

    git apply --check

Only syntactically valid patches are logged as successful.

---

# 10. SWE-Style Offline Evaluation

Implemented in:

    scripts/run_swe_refactor_offline.py

Example execution:

    python3 scripts/run_swe_refactor_offline.py \
      --dataset datasets/SWE-Refactor/pure_refactoring_data.json \
      --local-llm scripts/local_llm.py \
      --model deepseek-coder:1.3b \
      --project commons-io \
      --limit 20 \
      --retries 0 \
      --out /tmp/swe_method_commons_io.jsonl

For each dataset instance, the system:

- Extracts the target file
- Sends snippet to the local LLM
- Generates unified diff
- Sanitizes the patch
- Validates using `git apply --check`
- Logs:
  - ok (boolean)
  - added lines
  - deleted lines
  - error (if any)

This enables structured experiment tracking and large-scale evaluation.

---

# 11. What Is Currently Working

- Repository-aware AST extraction pipeline
- Structural summary generation
- Local LLM inference via Ollama
- Unified diff extraction
- Patch sanitization
- git apply validation
- Offline SWE-style experiment loop
- JSONL structured logging

The end-to-end refactoring evaluation pipeline is operational.

---

# 12. Known Limitations

- Compilation validation not yet integrated
- Test-suite validation not yet integrated
- Large-file refactoring may produce unstable diffs
- Structural delta comparison is not fully automated
- Method-level targeting is not yet implemented

These are active areas of ongoing research development.

---

# 13. Planned Research Extensions

1. Integrate compilation validation (mvn compile)
2. Integrate test execution (mvn test)
3. Automate structural before/after comparison
4. Move from file-level to method-level refactoring
5. Compare multiple local LLM models
6. Conduct statistical analysis across larger datasets
7. Evaluate behavior-preservation reliability

---

# 14. Research Contribution

This project contributes:

- A modular repository-aware evaluation infrastructure
- Fully offline reproducible LLM refactoring experiments
- Diff-based validation framework
- AST-based structural measurement methodology
- SWE-style dataset integration

It establishes the experimental foundation necessary for rigorous evaluation of AI-driven refactoring systems.

---

# 15. Reproducibility

Environment:

- macOS
- Python 3.10+
- Ollama
- deepseek-coder model

All experiments can be reproduced locally without external APIs.

---

# Dataset Setup

This repository does **not** store the SWE-Refactor dataset directly.

The dataset file:

    datasets/SWE-Refactor/pure_refactoring_data.json

is intentionally excluded from version control because it exceeds GitHub’s recommended file size limits and is treated as external research data.

## How to Prepare the Dataset

1. Obtain the SWE-Refactor dataset (JSON format).
2. Create the directory structure:

       datasets/SWE-Refactor/

3. Place the dataset file inside:

       datasets/SWE-Refactor/pure_refactoring_data.json

The evaluation script expects the dataset at this exact path.

## Expected Script Usage

Example execution:

    python3 scripts/run_swe_refactor_offline.py \
      --dataset datasets/SWE-Refactor/pure_refactoring_data.json \
      --local-llm scripts/local_llm.py \
      --model deepseek-coder:1.3b \
      --project commons-io \
      --limit 20 \
      --retries 0 \
      --out /tmp/swe_method_commons_io.jsonl

If the dataset file is not present at the expected location, the script will fail.

---

This design keeps the repository lightweight while ensuring reproducibility of experiments.

---

# 16. Conclusion

This repository provides a research-grade infrastructure for evaluating LLM-based refactoring at the repository level.

It goes beyond simple code generation by:

- Validating patches automatically
- Logging structured experiment results
- Enabling structural analysis
- Supporting benchmark-style evaluation

This system forms the foundation for deeper investigation into repository-aware, behavior-preserving AI refactoring systems.