import json
import os
import re
import subprocess
from typing import Dict, Tuple, Callable
from compile_experiment import checkout_previous_commit, \
    switch_java_version, compile_project

def compile_and_test_refactoring(refactoring: Dict, project_prefix_path: str, project_path: str) -> Tuple[bool, bool, str]:
    """
    If both 'refactoringMinerResult' and 'compileAndTestResult' are True in the input,
    return them immediately. Otherwise, dispatch based on the refactoring type.

    :param refactoring: A dict containing refactoring info.
    :return: A tuple (refactoringMinerResult, compileAndTestResult).
    :raises ValueError: If refactoring['type'] is not supported.
    """
    # Read existing results (default to False if missing)
    miner_result = refactoring.get("refactoringMinerResult", False)
    test_result = refactoring.get("compileAndTestResult", False)

    # If both checks passed, return immediately
    if not (miner_result and test_result):
        return miner_result, test_result, ""

    # Determine which evaluator to call based on the refactoring type
    ref_type = refactoring.get("type")
    evaluators: Dict[str, Callable[[Dict, str, str], Tuple[bool, bool, str]]] = {
        "Extract Method": eval_extract_method,
        "Inline Method": eval_inline_method,
        "Move Method": eval_move_method,
        "Extract And Move Method": eval_extract_and_move_method,
        "Move And Inline Method": lambda _, a, b: (False, False, ""),
        "Move And Rename Method": eval_move_method,
    }

    evaluator = evaluators.get(ref_type)
    if evaluator is None:
        # Unknown refactoring type
        raise ValueError(f"Unsupported refactoring type: {ref_type!r}")

    # Call the appropriate evaluation function
    return evaluator(refactoring, project_prefix_path, project_path)


def eval_extract_method(refactoring: Dict, project_prefix_path: str, project_path: str) -> Tuple[bool, bool, str]:
    """
    Evaluate the result of an 'Extract Method' refactoring.

    :param refactoring: A dictionary containing refactoring metadata, including the refactored code.
    :param project_path: Absolute path to the project root.
    :param project_prefix_path: Path prefix used during compilation.
    :return: A tuple (refactoring success, compilation success).
    """
    refactored_code_str = refactoring.get("refactoredCode")
    refactoring_id = refactoring.get("uniqueId")
    print(f"Calling eval_extract_method for refactoring ID: {refactoring_id}")

    # Step 1: Extract fields from the refactored code
    success, fields = extract_fields_for_extract_method(refactored_code_str)
    if not success:
        print(fields)  # likely an error message
        return False, False, ""
    if fields == "no need to refactor.":
        print("Refactoring skipped: no need to refactor.")
        return True, True, ""

    refactored_method_code = fields['refactored_method_code']
    return True, True, refactored_method_code
    # Step 2: Prepare file paths and retrieve the previous commit
    full_file_path = os.path.join(project_path, refactoring['filePathBefore'])
    checkout_previous_commit(refactoring['commitId'], project_path)

    # Replace the original method code with the refactored method code
    updated_source_code = refactoring['sourceCodeBeforeForWhole'].replace(
        refactoring['sourceCodeBeforeRefactoring'], refactored_method_code
    )

    # Step 3: Evaluate refactoring correctness
    refactoring_result, refactoring_msg = check_refactoring_for_single_file(
        project_prefix_path, project_path, full_file_path,
        refactoring['sourceCodeBeforeForWhole'], updated_source_code,
        "Extract Method"
    )

    # Step 4: Write the updated code back to file and compile the project
    with open(full_file_path, 'w', encoding='utf-8') as f:
        f.write(updated_source_code)

    compile_result, compile_log = compile_project_for_base(project_path, refactoring['compileJDK'])

    print("Refactoring validation message:", refactoring_msg)
    print("Compilation log:", compile_log)

    return refactoring_result, compile_result

def compile_project_for_base(project_path, compile_jdk):
    try:
        os.chdir(project_path)
        print(f"Switched to project directory: {project_path}")
    except Exception as e:
        print(f"Failed to switch to directory {project_path}: {e}")
        return False, "Failed to switch to directory."
    switch_java_version(compile_jdk)
    compile_re, log = compile_project()
    switch_java_version(17)
    return compile_re, log

def extract_fields_for_extract_method(refactored_code_str):
    """extract the fields from the refactored code string"""
    print("call extract_fields_for_extract_method, refactored_code_str:", refactored_code_str)

    # Step 1: Check empty
    if not refactored_code_str.strip():
        return False, "The refactored code is empty."


    cleaned_blocks = get_cleaned_blocks(refactored_code_str)

    if len(cleaned_blocks) < 1:
        return False, f"Expected at least 1 section refactored method, but got {len(cleaned_blocks)}."
    refactored_method_code = cleaned_blocks[-1]
    return True, {
        "refactored_method_code": refactored_method_code
    }

def get_cleaned_blocks(refactored_code_str):
    # Step 3: Use regex to extract the 3 parts between separators
    blocks = re.split(r"#{26}", refactored_code_str.strip())

    # Clean up each block (remove ``` and ```java if present)
    cleaned_blocks = []
    for block in blocks:
        code = block.strip()
        # Remove wrapping ``` or ```java
        if code.startswith("```java"):
            code = code[len("```java"):].strip()
        elif code.startswith("```"):
            code = code[len("```"):].strip()
        if code.endswith("```"):
            code = code[:-len("```")].strip()
        if code == "refactored_method_code":
            continue
        cleaned_blocks.append(code)
    # Remove empty blocks
    if is_java_code(cleaned_blocks[-1]):
        return cleaned_blocks
    return cleaned_blocks[:-1]  # Exclude the last block which is empty

def is_java_code(code_str):
    method_pattern = re.compile(
        r'\b(public|private|protected|static|final|abstract)\s+[\w<>[\]]+\s+\w+\s*\([^)]*\)\s*\{'
    )
    if method_pattern.search(code_str):
        return True

def check_refactoring_for_single_file(project_prefix_path, project_path, origin_file_path, origin_code, origin_refactored_code, refactoring_type):
    file_path_before = f"{project_prefix_path}/data/tmp/source_code_before_for_whole.txt"
    file_path_after = f"{project_prefix_path}/data/tmp/source_code_after_for_whole.txt"
    with open(file_path_before, "w", encoding="utf-8") as file:
        file.write(origin_code)
    with open(file_path_after, "w", encoding="utf-8") as file:
        file.write(origin_refactored_code)
    return check_refactoring_result_all(project_prefix_path, project_path, refactoring_type, origin_file_path, file_path_before, file_path_after)

def check_refactoring_result_all(project_prefix_path, project_path, refactoring_type, origin_file_path, file_path_before, file_path_after, target_file_path = None):
    try:
        os.chdir(project_path)
        print(f"Switched to project directory: {project_path}")
    except Exception as e:
        print(f"Failed to switch to directory {project_path}: {e}")
    switch_java_version(17)
    try:
        os.chdir(project_prefix_path)
        print(f"Switched to project directory: {project_prefix_path}")
    except Exception as e:
        print(f"Failed to switch to directory {project_prefix_path}: {e}")

    if target_file_path:
        exe_result = subprocess.run(
            [f"./data/tools/RefactoringMiner-3.0.10/bin/RefactoringMiner", "-spr", origin_file_path,
             file_path_before,
             target_file_path, file_path_after, refactoring_type], capture_output=True, text=True)
    else:
        exe_result = subprocess.run(
            ["./data/tools/RefactoringMiner-3.0.10/bin/RefactoringMiner", "-scr", origin_file_path, file_path_before,
             file_path_after, refactoring_type], capture_output=True, text=True)
    if exe_result.returncode != 0:
        print(f"Error running RefactoringMiner: {exe_result.stderr}")
        return False, "RefactoringMiner execution failed."
    refactoring_result = exe_result.stdout
    last_line = refactoring_result.strip().split('\n')[-1]
    result_word = [word for word in last_line.split()]
    if result_word[0] == "true":
        REFACTORING_RESULT = True
        return True, " the " + refactoring_type + " operation is successful."
    else:
        REFACTORING_RESULT = False
        return False, " the code didn't perform " + refactoring_type + " operation."

def eval_inline_method(refactoring: Dict, project_prefix_path: str, project_path: str) -> Tuple[bool, bool, str]:
    ## Step 1: extract the file path, extract code, and refactored code from the refactored_code_str
    refactored_code_str = refactoring['refactoredCode']
    extract_result, generate_fields = extract_fields_for_extract_method(refactored_code_str)
    if not extract_result:
        print(generate_fields)
        return False, False, ""
    if generate_fields == "no need to refactor.":
        print(generate_fields)
        return True, True, ""
    refactored_class_code = generate_fields['refactored_method_code']
    return True, True, refactored_class_code
    ## Step 2: Check the target file path exists
    full_origin_file_path = os.path.join(project_path, refactoring['filePathBefore'])
    checkout_previous_commit(refactoring['commitId'], project_path)
    original_refactored_code = refactored_class_code
    refactoring_result, refactoring_message = check_refactoring_for_single_file(project_prefix_path, project_path, full_origin_file_path,
                                                                                refactoring[
                                                                                    'sourceCodeBeforeForWhole'],
                                                                                original_refactored_code,
                                                                                "Inline Method")
    with open(full_origin_file_path, 'w', encoding='utf-8') as f:
        f.write(original_refactored_code)
    compile_re, log = compile_project_for_base(project_path, refactoring['compileJDK'])
    print(refactoring_message, log)
    return refactoring_result, compile_re


def eval_extract_and_move_method(refactoring: Dict, project_prefix_path: str, project_path: str) -> Tuple[bool, bool, str]:
    refactored_code_str = refactoring.get("refactoredCode", "")
    extract_result, generate_fields = extract_fields_for_extract_and_move_method(refactored_code_str)
    if not extract_result:
        print(generate_fields)
        return False, False, ""
    if generate_fields == "no need to refactor.":
        print(generate_fields)
        return True, True, ""
    target_file_path = generate_fields['target_file_path']
    extracted_method_code = generate_fields['extracted_method_code']
    refactored_method_code = generate_fields['refactored_method_code']
    return True, True, extracted_method_code + "\n" + refactored_method_code
    ## Step 2: Check the target file path exists
    full_target_file_path = os.path.join(project_path, target_file_path)
    checkout_previous_commit(refactoring['commitId'], project_path)
    if not os.path.exists(full_target_file_path):
        print("The target file path does not exist, please move to an existing java file.")
        return False, False
    ## Step 3: Check the extracted method code and refactored method code
    origin_file_path = os.path.join(project_path, refactoring['filePathBefore'])

    try:
        with open(origin_file_path, 'r', encoding='utf-8') as f:
            origin_class_code = f.read()
    except Exception as e:
        print(f"Failed to read origin file: {e}")
        return False, False

    try:
        with open(full_target_file_path, 'r', encoding='utf-8') as f:
            target_class_code = f.read()
    except Exception as e:
        print(f"Failed to read target file: {e}")
        return False, False
    # Step 3: Extract the class name and package name
    origin_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)', origin_class_code)
    target_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)', target_class_code)
    if not origin_class_match or not target_class_match:
        print("Cannot extract class name from origin or target file.")
        return False, False
    target_class_name = target_class_match.group(2)
    target_package_match = re.search(r'package\s+([\w.]+);', target_class_code)
    target_package = target_package_match.group(1) if target_package_match else ""
    origin_package_match = re.search(r'package\s+([\w.]+);', origin_class_code)
    origin_package = origin_package_match.group(1) if origin_package_match else ""
    # Step 4: build origin_refactored_code
    origin_refactored_code = origin_class_code.replace(
        refactoring['sourceCodeBeforeRefactoring'], refactored_method_code)
    # get the package statement
    if target_package:
        import_target_class_stmt = f"import {target_package}.{target_class_name};"
    else:
        import_target_class_stmt = f"import {target_class_name};"
    if import_target_class_stmt not in origin_refactored_code:
        # insert import statement after package statement
        package_stmt_match = re.search(r'package\s+[^\n]+;', origin_refactored_code)
        if package_stmt_match:
            insert_pos = package_stmt_match.end()
            origin_refactored_code = (
                    origin_refactored_code[:insert_pos] +
                    f"\n{import_target_class_stmt}" +
                    origin_refactored_code[insert_pos:]
            )
        else:
            origin_refactored_code = import_target_class_stmt + "\n" + origin_refactored_code
    # Step 5: build target_refactored_code
    closing_brace_index = target_class_code.rfind('}')
    if closing_brace_index == -1:
        print("Cannot find closing brace in target class.")
        return False, False

    target_refactored_code = (
            target_class_code[:closing_brace_index] +
            "\n\n" + extracted_method_code + "\n" +
            target_class_code[closing_brace_index:]
    )
    # Step 6：handle import statements in target class
    imports_to_add = handle_import_in_target_class(extracted_method_code, origin_class_code, target_class_code, origin_package, origin_file_path)
    if imports_to_add:
        package_stmt_match = re.search(r'(package\s+[^\n]+;)', target_refactored_code)
        insert_pos = package_stmt_match.end() if package_stmt_match else 0
        imports_code = "\n" + "\n".join(imports_to_add) + "\n"
        target_refactored_code = (
                target_refactored_code[:insert_pos] + imports_code + target_refactored_code[insert_pos:]
        )
    # Step 7: 调用 RefactoringMiner 工具验证
    refactoring_type = "Extract And Move Method"
    check_refactoring_result, message = check_refactoring_for_multiple_files(
        project_prefix_path,
        project_path,
        origin_file_path,
        origin_refactored_code,
        full_target_file_path,
        target_refactored_code,
        refactoring_type
    )
    # Step 8: 编译
    # replace_java_code
    with open(full_target_file_path, 'w', encoding='utf-8') as f:
        f.write(target_refactored_code)
    with open(origin_file_path, 'w', encoding='utf-8') as f:
        f.write(origin_refactored_code)
    compile_re, log = compile_project_for_base(project_path, refactoring['compileJDK'])
    print(message)
    print(log)
    return check_refactoring_result, compile_re

def check_refactoring_for_multiple_files(project_prefix_path, project_path, origin_file_path, origin_refactored_code, target_file_path, target_refactored_code, refactoring_type):
    original_refactored_code_path_after = f"{project_prefix_path}/data/tmp/original_refactored_code.txt"
    target_refactored_code_path_after = f"{project_prefix_path}/data/tmp/target_refactored_code.txt"
    with open(original_refactored_code_path_after, "w", encoding="utf-8") as file:
        file.write(origin_refactored_code)
    with open(target_refactored_code_path_after, "w", encoding="utf-8") as file:
        file.write(target_refactored_code)
    return check_refactoring_result_all(project_prefix_path,project_path, refactoring_type, origin_file_path, original_refactored_code_path_after, target_refactored_code_path_after, target_file_path)

def extract_fields_for_extract_and_move_method(refactored_code_str):
    """
        Check the refactoring result of the extract and move method refactoring.
        """
    print("call extract_fields_for_extract_and_move_method, refactored_code_str:", refactored_code_str)

    # Step 1: Check empty
    if not refactored_code_str.strip():
        return False, "The refactored code is empty."

    # Step 2: Check if it's a 'No need to refactor' response
    if refactored_code_str.strip().lower() == "no need to refactor.":
        return True, "No refactoring needed."

    cleaned_blocks = get_cleaned_blocks(refactored_code_str)

    # Only keep the last 3 sections
    if len(cleaned_blocks) < 3:
        return False, f"Expected at least 3 sections (file path, extracted method, refactored method), but got {len(cleaned_blocks)}."
    target_file_path = cleaned_blocks[-3]
    extracted_method_code = cleaned_blocks[-2]
    refactored_method_code = cleaned_blocks[-1]

    # Step 4: Check that target file path ends with .java
    if not target_file_path.endswith(".java"):
        return False, f"Invalid target file path: {target_file_path}"

    # Step 5: Check that extracted method contains 'public static'
    if "public static" not in extracted_method_code:
        return False, "Extracted method must be public static."

    # Step 6: Check if method name is used in refactored method code
    method_name_match = re.search(
        r"public\s+static\s+(<[^>]+>\s*)?[\w\[\]<>.]+\s+(\w+)\s*\(",
        extracted_method_code
    )
    if method_name_match:
        method_name = method_name_match.group(2)
        if method_name not in refactored_method_code:
            return False, f"Refactored code does not call extracted method '{method_name}'."
    else:
        return False, "Cannot extract method name from extracted method code."

    return True, {
        "target_file_path": target_file_path,
        "extracted_method_code": extracted_method_code,
        "refactored_method_code": refactored_method_code
    }

def handle_import_in_target_class(extracted_method_code, origin_class_code, target_class_code, origin_package, origin_file_path):
    # 1. 提取普通 import 和 static import
    origin_imports = re.findall(r'import\s+([\w.]+);', origin_class_code)
    origin_static_imports = re.findall(r'import\s+static\s+([\w.]+);', origin_class_code)

    target_existing_imports = set(re.findall(r'import\s+([\w.]+);', target_class_code))
    target_static_imports = set(re.findall(r'import\s+static\s+([\w.]+);', target_class_code))

    # 2. 提取 extracted_method_code 中的类型名（首字母大写），和静态方法名（可能是 assertThrows 等）
    used_types = set(re.findall(r'\b([A-Z][a-zA-Z0-9_]*)\b', extracted_method_code))
    used_methods = set(re.findall(r'\b([a-z][a-zA-Z0-9_]*)\s*\(', extracted_method_code))

    # 3. 构建 class_name → full_import 映射（来自 origin imports）
    candidate_imports = {}
    for full_import in origin_imports:
        class_name = full_import.split(".")[-1]
        candidate_imports[class_name] = full_import

    # 4. 同包类补充（未显式 import 的）
    relative_package_path = os.path.join(*origin_package.split("."))
    origin_module_root = origin_file_path[:origin_file_path.find("src/")]
    possible_source_roots = ["src/main/java", "src/test/java"]

    for src_root in possible_source_roots:
        package_dir = os.path.join(origin_module_root, src_root, relative_package_path)
        if os.path.exists(package_dir):
            for file in os.listdir(package_dir):
                if file.endswith(".java"):
                    class_name = file[:-5]
                    full_import = f"{origin_package}.{class_name}"
                    if class_name not in candidate_imports:
                        candidate_imports[class_name] = full_import

    # 5. 普通 import：根据 used_types 添加
    imports_to_add = []
    for class_name in used_types:
        if class_name in candidate_imports:
            full_import = candidate_imports[class_name]
            if full_import not in target_existing_imports:
                imports_to_add.append(f"import {full_import};")

    # 6. static import：从 origin static imports 中匹配 used method
    static_imports_to_add = []
    for static_import in origin_static_imports:
        static_member = static_import.split(".")[-1]  # 例如 assertThrows
        if static_member in used_methods and static_import not in target_static_imports:
            static_imports_to_add.append(f"import static {static_import};")
    # 7. 合并结果（先 static，再普通）
    return static_imports_to_add + imports_to_add

def eval_move_method(refactoring: Dict, project_prefix_path: str, project_path: str) -> Tuple[bool, bool, str]:
    """
    Evaluate the result of a 'Move And Rename Method' refactoring.
    """
    """ Check the refactoring result of the move method refactoring"""
    refactored_code_str = refactoring['refactoredCode']
    ## Step 1: extract the file path, extract code, and refactored code from the refactored_code_str
    extract_result, generate_fields = extract_fields_for_move_method(refactored_code_str)
    if not extract_result:
        print(generate_fields)
        return False, False, ""
    if generate_fields == "no need to refactor.":
        print(generate_fields)
        return True, True, ""
    return True, True, refactoring['sourceCodeBeforeRefactoring']
    target_file_path = generate_fields['target_file_path']
    moved_method_code = generate_fields['moved_method_code']
    refactored_method_code = generate_fields['refactored_method_code']
    ## Step 2: Check the target file path exists
    full_target_file_path = os.path.join(project_path, target_file_path)
    checkout_previous_commit(refactoring['commitId'], project_path)
    if not os.path.exists(full_target_file_path):
        print("The target file path does not exist, please move to an existing java file.")
        return False, False
    ## Step 3: Check the extracted method code and refactored method code
    origin_file_path = os.path.join(project_path, refactoring['filePathBefore'])

    try:
        with open(origin_file_path, 'r', encoding='utf-8') as f:
            origin_class_code = f.read()
    except Exception as e:
        print(f"Failed to read origin file: {e}")
        return False, False

    try:
        with open(full_target_file_path, 'r', encoding='utf-8') as f:
            target_class_code = f.read()
    except Exception as e:
        print(f"Failed to read target file: {e}")
        return False, False
    # Step 3: Extract the class name and package name
    origin_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)',
                                   origin_class_code)
    target_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)',
                                   target_class_code)
    if not origin_class_match or not target_class_match:
        print("Cannot extract class name from origin or target file.")
        return False, False
    target_class_name = target_class_match.group(2)
    target_package_match = re.search(r'package\s+([\w.]+);', target_class_code)
    target_package = target_package_match.group(1) if target_package_match else ""
    origin_package_match = re.search(r'package\s+([\w.]+);', origin_class_code)
    origin_package = origin_package_match.group(1) if origin_package_match else ""
    # Step 4: build origin_refactored_code
    origin_refactored_code = origin_class_code.replace(
        refactoring['sourceCodeBeforeRefactoring'], refactored_method_code)
    origin_refactored_code_for_move = origin_class_code.replace(
        refactoring['sourceCodeBeforeRefactoring'], "")
    # get the package statement
    if target_package:
        import_target_class_stmt = f"import {target_package}.{target_class_name};"
    else:
        import_target_class_stmt = f"import {target_class_name};"
    if import_target_class_stmt not in origin_refactored_code:
        # insert import statement after package statement
        package_stmt_match = re.search(r'package\s+[^\n]+;', origin_refactored_code)
        if package_stmt_match:
            insert_pos = package_stmt_match.end()
            origin_refactored_code = (
                    origin_refactored_code[:insert_pos] +
                    f"\n{import_target_class_stmt}" +
                    origin_refactored_code[insert_pos:]
            )
        else:
            origin_refactored_code = import_target_class_stmt + "\n" + origin_refactored_code
    # Step 5: build target_refactored_code
    closing_brace_index = target_class_code.rfind('}')
    if closing_brace_index == -1:
        print("Cannot find closing brace in target class.")
        return False, False

    target_refactored_code = (
            target_class_code[:closing_brace_index] +
            "\n\n" + moved_method_code + "\n" +
            target_class_code[closing_brace_index:]
    )
    # Step 6：handle import statements in target class
    imports_to_add = handle_import_in_target_class(moved_method_code, origin_class_code, target_class_code,
                                                   origin_package, origin_file_path)
    if imports_to_add:
        package_stmt_match = re.search(r'(package\s+[^\n]+;)', target_refactored_code)
        insert_pos = package_stmt_match.end() if package_stmt_match else 0
        imports_code = "\n" + "\n".join(imports_to_add) + "\n"
        target_refactored_code = (
                target_refactored_code[:insert_pos] + imports_code + target_refactored_code[insert_pos:]
        )
    # Step 7: 调用 RefactoringMiner 工具验证
    refactoring_type = refactoring['type']
    check_refactoring_result, message = check_refactoring_for_multiple_files(
        project_prefix_path,
        project_path,
        origin_file_path,
        origin_refactored_code_for_move,
        full_target_file_path,
        target_refactored_code,
        refactoring_type
    )
    # Step 8: 编译
    # replace_java_code
    with open(full_target_file_path, 'w', encoding='utf-8') as f:
        f.write(target_refactored_code)
    with open(origin_file_path, 'w', encoding='utf-8') as f:
        f.write(origin_refactored_code)
    compile_re, log = compile_project_for_base(project_path, refactoring['compileJDK'])
    print(message, log)
    return check_refactoring_result, compile_re

def extract_fields_for_move_method(refactored_code_str):
    """ Check the refactoring result of the move method refactoring."""
    print("call extract_fields_for_move_method, refactored_code_str:", refactored_code_str)

    # Step 1: Check empty
    if not refactored_code_str.strip():
        return False, "The refactored code is empty."

    # Step 2: Check if it's a 'No need to refactor' response
    if refactored_code_str.strip().lower() == "no need to refactor.":
        return True, "No refactoring needed."

    cleaned_blocks = get_cleaned_blocks(refactored_code_str)

    # Only keep the last 3 sections
    if len(cleaned_blocks) < 3:
        return False, f"Expected at least 3 sections (file path, moved class, refactored method), but got {len(cleaned_blocks)}."
    target_file_path = cleaned_blocks[-3]
    moved_method_code = extract_class_body(cleaned_blocks[-2])
    refactored_method_code = cleaned_blocks[-1]

    # Step 4: Check that target file path ends with .java
    if not target_file_path.endswith(".java"):
        return False, f"Invalid target file path: {target_file_path}"

    # Step 5: Check that extracted method contains 'public static'
    if "public static" not in moved_method_code:
        return False, "Moved method must be public static."

    # Step 6: Check if method name is used in refactored method code
    method_name_match = re.search(r"public static\s+\w+\s+(\w+)\s*\(", moved_method_code)
    if method_name_match:
        method_name = method_name_match.group(1)
        if method_name not in refactored_method_code:
            return False, f"Refactored code does not call moved method '{method_name}'."
    else:
        return False, "Cannot extract method name from moved method code."

    return True, {
        "target_file_path": target_file_path,
        "moved_method_code": moved_method_code,
        "refactored_method_code": refactored_method_code
    }

def extract_class_body(java_code: str) -> str:
    # 匹配第一个 class 定义后的大括号中的内容（非递归，适合简单文件）
    match = re.search(r'class\s+\w+\s*{(.*)}\s*$', java_code, re.DOTALL)
    if match:
        class_body = match.group(1).strip()
        return class_body
    return java_code

def main():
    project_prefix_path = '/Users/yisenxu/Downloads/Research/SOEN6491/Code/refactoring_data_analysis'
    project_name = "pmd"
    model_name_list = [
        "gpt-4o-mini",
        "gpt-3.5-turbo-0125",
        "deepseek-chat",
        "qwen2.5-coder:14b",
        "qwen2.5-coder:7b",
        "deepseek-coder-v2:16b",
        "deepseek-coder:6.7b",
        "codellama:13b",
        "codellama:7b"
    ]
    for model_name in model_name_list:
        # start = 0
        # end = 90
        # file_path = f'{project_prefix_path}/data/{project_name}/{project_name}_baseline_result_{model_name}.json'
        # output_path = f'{project_prefix_path}/data/{project_name}/{project_name}_baseline_result_{model_name}_rm_compile_result_{start}_{end}.json'
        file_path = f'{project_prefix_path}/benchmark/{project_name}/{project_name}_baseline_result_{model_name}_rm_compile_result_merge.json'
        output_path = f'{project_prefix_path}/benchmark/{project_name}/{project_name}_baseline_result_{model_name}_rm_compile_result_merge_with_code.json'
        project_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/{project_name}'
        with open(file_path, 'r') as file:
            data = json.load(file)

        # index_ref = 0
        refactoring_results = []
        for refactoring in data:
            # if start <= index_ref < end:
            refactoring_miner_result, compile_and_test_result, after_code = compile_and_test_refactoring(refactoring, project_prefix_path, project_path)
            refactoring['refactoringMinerResult'] = refactoring_miner_result
            refactoring['compileAndTestResult'] = compile_and_test_result
            refactoring['toolAfterCode'] = after_code
            refactoring_results.append(refactoring)
            # index_ref += 1

        with open(output_path, 'w') as file:
            json.dump(refactoring_results, file)

if __name__ == "__main__":
    main()
