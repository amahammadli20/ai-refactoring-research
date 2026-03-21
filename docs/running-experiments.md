# Running Experiments

This document describes how to reproduce the main refactoring experiments in this repository, including method extraction, local LLM-based refactoring, patch sanitization, validation, and result logging.

## Overview

The experimental pipeline is designed to evaluate repository-aware LLM-based refactoring on real Java repositories. The workflow operates at the method level and records structured results in JSONL format for later analysis.

### Pipeline stages

1. Extract candidate Java methods from a repository
2. Select method samples for evaluation
3. Send method bodies to a local LLM (via Ollama)
4. Generate refactored code suggestions
5. Sanitize model output (remove markdown fences / commentary)
6. Reinsert the refactored method into the original file
7. Validate changes using unified diff checks and compilation
8. Log experiment results as JSONL

---

## Repository structure

- `scripts/` — Main experiment scripts for extraction, refactoring, sanitization, reinsertion, and offline evaluation
- `results/` — JSONL logs from experiment runs
- `docs/` — Research and technical documentation
- `modules/ast-extractor/` — AST extraction module for repository-aware parsing
- `datasets/SWE-Refactor/` — Dataset and supporting experimental assets

---

## Prerequisites

Before running experiments, make sure the following are installed:

- Python 3.10+
- Git
- Java / Maven (for compilation validation on Java repositories)
- Ollama
- A local code model (for example `deepseek-coder:6.7b`)

### Install Python dependencies

Run:

`pip install -r requirements.txt`

### Verify Ollama

Run:

`ollama list`

Example model used in this project:

`ollama pull deepseek-coder:6.7b`

---

## Step 1: Extract candidate methods

Use the extraction scripts to collect method-level candidates from a target Java repository.

Example command:

`python scripts/extract_methods_java.py`

This stage scans Java files, identifies method boundaries, and prepares method-level records for refactoring experiments.

---

## Step 2: Run local LLM refactoring

The main refactoring stage sends extracted method bodies to a local LLM through Ollama and captures the generated refactored output.

Example command:

`python scripts/llm_refactor_block_ollama.py`

This stage typically performs:

- prompt construction
- local model invocation
- response capture
- intermediate logging

---

## Step 3: Sanitize model output

LLM outputs may contain markdown fences, commentary text, or formatting artifacts. These must be removed before validation.

Example command:

`python scripts/sanitize_block.py`

This stage ensures that the generated output can be safely reinserted into source files.

---

## Step 4: Reinsert refactored method

After sanitization, the refactored method is injected back into the original Java file.

Example command:

`python scripts/inject_method_body.py`

If additional replacement logic is needed:

`python scripts/replace_method_block.py`

This stage reconstructs the modified source file for downstream validation.

---

## Step 5: Validate generated changes

Validation is performed using diff-based and repository-aware checks.

Typical checks include:

- unified diff generation
- patch validation
- `git apply --check`
- Maven compilation (when applicable)

The offline evaluation script coordinates these checks:

`python scripts/run_swe_refactor_offline.py`

---

## Step 6: Review results

All experiment outputs are logged in the `results/` directory as JSONL files.

Example files:

- `results/exp_commons_io_1p3b.jsonl`
- `results/exp_commons_lang_6p7b.jsonl`
- `results/exp_guava_6p7b.jsonl`

Typical logged fields include:

- repository name
- sample identifier
- model name
- patch validity
- lines added / deleted
- guardrail failure information
- error messages (if any)

---

## Reproducing the main experiments

The primary experiments in this project were conducted on multiple Java repositories, including:

- Apache Commons IO
- Apache Commons Lang
- Guava

Representative configurations include:

- `deepseek-coder:1.3b`
- `deepseek-coder:6.7b`
- comparative runs with additional open-weight models

The recommended reproduction workflow is:

1. Prepare or clone the target repository
2. Extract method-level candidates
3. Run local LLM refactoring
4. Sanitize outputs
5. Reinsert generated methods
6. Run validation
7. Save JSONL results in `results/`
8. Analyze aggregated metrics

---

## Notes on reproducibility

This repository contains experimental logs and modular scripts, but exact runtime behavior may vary depending on:

- the local Ollama version
- model version / quantization
- repository checkout state
- selected sample set
- Java / Maven environment

For this reason, the JSONL logs in `results/` should be treated as the canonical experimental artifacts used for the paper’s reported findings.

---

## Recommended next step

To regenerate the summary tables used in the paper, run the analysis script over the JSONL files in `results/`.