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

---

# 17. Recent Development Progress (Method-Level Refactoring Pipeline)

As part of the ongoing development of the evaluation infrastructure, an experimental **method-level refactoring pipeline** has been implemented.

This extension moves beyond file-level refactoring and enables targeted transformation of individual Java methods inside a repository.

The goal of this stage is to test whether local LLMs can safely refactor specific code regions while preserving compilation and behavioral correctness.

---

## Method-Level Refactoring Workflow

The implemented workflow consists of the following stages:

### 1. Repository AST Extraction

Java repositories are parsed using the Tree-sitter-based extraction module.  
The pipeline produces a JSON file (`commons_io_methods.json`) containing metadata for each discovered method, including:

- file path  
- method signature  
- byte range  
- method body  
- structural metadata  

---

### 2. Method Selection

Candidate methods are selected using heuristic filters such as:

- method body length (e.g., 400–2000 characters)  
- non-constructor methods  
- valid source locations  

This allows controlled sampling of refactoring targets.

---

### 3. Method Body Extraction

The target method body is extracted from the repository and saved to a temporary file.

Example:

```

/tmp/method_block_1766.txt

```

---

### 4. Local LLM Refactoring

The extracted method body is sent to a local LLM via Ollama.

Tested models:

- `deepseek-coder:1.3b`  
- `deepseek-coder:6.7b`  

The model is prompted to produce a refactored version of the method body while preserving behavior.

---

### 5. Output Sanitization

Because LLM outputs frequently contain:

- markdown code fences  
- commentary text  
- malformed structures  

a sanitization step is applied to extract a valid Java code block.

Implemented in:

```

scripts/sanitize_block.py

```

---

### 6. Method Replacement

The sanitized refactored method body is injected back into the original source file using byte-range replacement.

Implemented in:

```

scripts/replace_method_block.py

```

---

### 7. Patch Verification

The modified source file is compared against the original using a unified diff.

This allows inspection of the exact transformation produced by the LLM.

---

### 8. Compilation Validation

The modified repository is compiled and tested using Maven:

```

mvn -Dtest=<TestClass> test

```

This verifies whether the generated refactoring preserves syntactic correctness and test behavior.

---

## Supporting Scripts

The method-level pipeline is implemented through the following helper scripts:

```

scripts/extract_methods_java.py
scripts/inject_method_body.py
scripts/llm_refactor_block_ollama.py
scripts/replace_method_block.py
scripts/sanitize_block.py

```

These scripts together enable automated extraction, refactoring, and reinsertion of method bodies within a repository.

---

## Experimental Observations

During early experiments several important behaviors were observed:

- Smaller LLM models often produce invalid or incomplete refactorings.  
- LLM outputs frequently include non-code artifacts that must be sanitized.  
- Tokenization artifacts from some models can introduce illegal characters in Java source files.  
- Even small refactorings may break compilation if method boundaries are not preserved precisely.  

These findings highlight the need for robust validation mechanisms when evaluating AI-generated refactorings.

---

## Research Impact

The addition of method-level refactoring support significantly expands the evaluation capabilities of the system.

It enables experiments that answer questions such as:

- Can LLMs safely refactor individual methods?  
- How often do generated refactorings preserve compilation?  
- How stable are LLM-generated code transformations?  

This capability will support future experiments involving:

- automated large-scale refactoring evaluation  
- structural impact analysis  
- behavioral preservation studies  

---

# 18. Experimental Results (Multi-Repository Evaluation)

To validate the robustness of the refactoring pipeline, a set of controlled experiments were conducted across multiple open-source Java repositories.

The goal of these experiments was to evaluate whether the system can consistently generate **syntactically valid patches** across different repositories using local LLM models.

---

## Experiment Configuration

Dataset: SWE-Refactor  
Sample size: 20 instances per repository  

Models tested:

- DeepSeek-Coder 1.3B  
- DeepSeek-Coder 6.7B  

Validation method:

- Patch sanitization
- `git apply --check` validation

Only patches that passed the validation stage were counted as successful.

---

## Results Summary

The following table summarizes the patch validation results across multiple repositories and models.

| Repository | Model | Samples | Valid Patches | Status | Notes |
|---|---|---|---|---|---|
| commons-io | DeepSeek-Coder 1.3B | 20 | 20/20 | success | patch validation successful |
| commons-lang | DeepSeek-Coder 1.3B | 20 | 20/20 | success | stable diff generation |
| commons-collections | DeepSeek-Coder 1.3B | 20 | 0/0 | skipped | dataset contains no matching instances |
| guava | DeepSeek-Coder 1.3B | 20 | 17/20 | partial | 3 patches blocked by deletion-ratio guardrail |
| commons-io | DeepSeek-Coder 6.7B | 20 | 20/20 | success | model comparison experiment |

---

## Observations

Several important behaviors were observed during these experiments:

- The refactoring pipeline successfully generated valid patches across multiple repositories.
- Guardrail mechanisms prevented potentially unsafe transformations in several cases.
- Larger repositories such as **Guava** exhibited slightly higher failure rates due to stricter safety constraints.
- Both tested models were capable of producing syntactically valid refactorings under controlled conditions.

Overall, the experiments demonstrate that local LLMs can reliably generate diff-valid refactorings across multiple repositories when combined with patch sanitization and guardrail validation.

These results demonstrate that the proposed evaluation pipeline enables systematic comparison of multiple LLM models for automated refactoring tasks across real-world repositories.

---
## Refactoring Evaluation Pipeline

```
AI-Driven Refactoring Evaluation Pipeline

Refactoring Evaluation Framework
(ai-refactoring-research)
        │
        │ generates refactoring patches
        ▼
Patch Sanitization
        │
        ▼
Patch Validation
(git apply --check)
        │
        │ validated experiment outputs
        ▼
Experiment Results
(results/*.jsonl)
        │
        │ manual validation
        ▼
Target Repositories
(refactor-experiments)
   ├ commons-io
   ├ commons-lang
   └ guava
        │
        ▼
Compilation & Test Validation
(mvn compile / mvn test)
```