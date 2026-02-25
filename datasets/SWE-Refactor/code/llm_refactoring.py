import json
import os
import re
import subprocess

from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from tqdm import tqdm

from compile_experiment import checkout_previous_commit, \
    switch_java_version, compile_project
from project_util import get_project_structure

project_prefix_path = '/Users/yisenxu/Downloads/Research/SOEN6491/Code/refactoring_benchmark'
# OpenAI API key
# model_name = "qwen2.5-coder:7b"
# model_name = "codellama:7b"
# model_name = "deepseek-coder:6.7b"
model_name = "gpt-3.5-turbo-0125"
# model_name = "gpt-4o-mini"
# model_name = "deepseek-chat"
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
# llm = ChatOpenAI(model=model_name, temperature=0, api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
# llm = ChatOllama(model=model_name, temperature=0, base_url="http://localhost:11434")
# Initialize the LLM
llm = ChatOpenAI(model=model_name, temperature=0, openai_api_key=OPENAI_API_KEY)
# llm = ChatOpenAI(model=model_name, temperature=0, openai_api_key=OPENAI_API_KEY)
REFACTORING_RESULT = False
project_name = "mockito"

file_path = f'{project_prefix_path}/data/{project_name}/{project_name}_pure_refactoring_data.json'
project_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/{project_name}'
with open(file_path, 'r') as file:
    data = json.load(file)


# Function to load the prompt template from a file
def load_prompt_template(prompt_file_path):
    with open(prompt_file_path, 'r') as prompt_file:
        return prompt_file.read()


# Function to save refactoring results to a file
def save_refactoring_results(output_file_path, results):
    with open(output_file_path, 'w') as output_file:
        json.dump(results, output_file, indent=4)


def check_move_method_refactoring_compile_result (refactoring_id, refactoring_object, refactored_code_str: str):
    """ Check the refactoring result of the move method refactoring"""
    print("call check_move_method_refactoring_compile_result, refactoring_id:", refactoring_id)
    ## Step 1: extract the file path, extract code, and refactored code from the refactored_code_str
    extract_result, generate_fields = extract_fields_for_move_method(refactored_code_str)
    if not extract_result:
        return False, generate_fields, False, generate_fields
    if generate_fields == "no need to refactor.":
        return True, "No refactoring needed.", True, "No refactoring needed."
    target_file_path = generate_fields['target_file_path']
    moved_method_code = generate_fields['moved_method_code']
    refactored_method_code = generate_fields['refactored_method_code']
    ## Step 2: Check the target file path exists
    full_target_file_path = os.path.join(project_path, target_file_path)
    checkout_previous_commit(refactoring_object['commitId'], project_path)
    if not os.path.exists(full_target_file_path):
        return False, "The target file path does not exist, please move to an existing java file.", False, "The target file path does not exist, please move to an existing java file."
    ## Step 3: Check the extracted method code and refactored method code
    origin_file_path = os.path.join(project_path, refactoring_object['filePathBefore'])

    try:
        with open(origin_file_path, 'r', encoding='utf-8') as f:
            origin_class_code = f.read()
    except Exception as e:
        return False, f"Failed to read origin file: {e}", False, f"Failed to read origin file: {e}"

    try:
        with open(full_target_file_path, 'r', encoding='utf-8') as f:
            target_class_code = f.read()
    except Exception as e:
        return False, f"Failed to read target file: {e}", False, f"Failed to read target file: {e}"
    # Step 3: Extract the class name and package name
    origin_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)', origin_class_code)
    target_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)', target_class_code)
    if not origin_class_match or not target_class_match:
        return False, "Cannot extract class name from origin or target file.", False, "Cannot extract class name from origin or target file."
    target_class_name = target_class_match.group(1)
    target_package_match = re.search(r'package\s+([\w\.]+);', target_class_code)
    target_package = target_package_match.group(1) if target_package_match else ""
    origin_package_match = re.search(r'package\s+([\w\.]+);', origin_class_code)
    origin_package = origin_package_match.group(1) if origin_package_match else ""
    # Step 4: build origin_refactored_code
    origin_refactored_code = origin_class_code.replace(
        refactoring_object['sourceCodeBeforeRefactoring'], refactored_method_code)
    origin_refactored_code_for_move = origin_class_code.replace(
        refactoring_object['sourceCodeBeforeRefactoring'], "")
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
        return False, "Cannot find closing brace in target class."

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
    refactoring_type = refactoring_object['type']
    check_refactoring_result, message = check_refactoring_for_multiple_files(
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
    compile_re, log = compile_project_for_base(refactoring_object['compileJDK'])
    return check_refactoring_result, message, compile_re, log

def extract_class_body(java_code: str) -> str:
    # 匹配第一个 class 定义后的大括号中的内容（非递归，适合简单文件）
    match = re.search(r'class\s+\w+\s*{(.*)}\s*$', java_code, re.DOTALL)
    if match:
        class_body = match.group(1).strip()
        return class_body
    return java_code

def check_inline_method_refactoring_compile_result(refactoring_id, refactoring_object, refactored_code_str: str):
    ## Check the refactoring result of the inline method refactoring
    print("call check_inline_method_refactoring_compile_result, refactoring_id:", refactoring_id)
    ## Step 1: extract the file path, extract code, and refactored code from the refactored_code_str
    extract_result, generate_fields = extract_fields_for_extract_method(refactored_code_str)
    if not extract_result:
        return False, generate_fields, False, generate_fields
    if generate_fields == "no need to refactor.":
        return True, "No refactoring needed.", True, "No refactoring needed."
    refactored_class_code = generate_fields['refactored_method_code']
    ## Step 2: Check the target file path exists
    full_origin_file_path = os.path.join(project_path, refactoring_object['filePathBefore'])
    checkout_previous_commit(refactoring_object['commitId'], project_path)
    original_refactored_code = refactored_class_code
    refactoring_result, refactoring_message = check_refactoring_for_single_file(full_origin_file_path,
                                                                                refactoring_object[
                                                                                    'sourceCodeBeforeForWhole'],
                                                                                original_refactored_code,
                                                                                "Inline Method")
    with open(full_origin_file_path, 'w', encoding='utf-8') as f:
        f.write(original_refactored_code)
    compile_re, log = compile_project_for_base(refactoring_object['compileJDK'])
    return refactoring_result, refactoring_message, compile_re, log


def check_extract_method_refactoring_compile_result(refactoring_id, refactoring_object, refactored_code_str: str):
    ## Check the refactoring result of the extract method refactoring
    print("call check_extract_method_refactoring_compile_result, refactoring_id:", refactoring_id)
    ## Step 1: extract the file path, extract code, and refactored code from the refactored_code_str
    extract_result, generate_fields = extract_fields_for_extract_method(refactored_code_str)
    if not extract_result:
        return False, generate_fields, False, generate_fields
    if generate_fields == "no need to refactor.":
        return True, "No refactoring needed.", True, "No refactoring needed."
    refactored_method_code = generate_fields['refactored_method_code']
    ## Step 2: Check the target file path exists
    full_origin_file_path = os.path.join(project_path, refactoring_object['filePathBefore'])
    checkout_previous_commit(refactoring_object['commitId'], project_path)
    original_refactored_code = refactoring_object['sourceCodeBeforeForWhole'].replace(
        refactoring_object['sourceCodeBeforeRefactoring'], refactored_method_code)
    refactoring_result, refactoring_message = check_refactoring_for_single_file(full_origin_file_path, refactoring_object['sourceCodeBeforeForWhole'], original_refactored_code, "Extract Method")
    with open(full_origin_file_path, 'w', encoding='utf-8') as f:
        f.write(original_refactored_code)
    compile_re, log = compile_project_for_base(refactoring_object['compileJDK'])
    return refactoring_result, refactoring_message, compile_re, log


def compile_project_for_base(compile_jdk):
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


def check_extract_and_move_method_refactoring_compile_result(refactoring_id, refactoring_object, refactored_code_str: str):
    ## Check the refactoring result of the extract and move method refactoring
    print("call check_extract_and_move_method_refactoring_compile_result, refactoring_id:", refactoring_id)
    ## Step 1: extract the file path, extract code, and refactored code from the refactored_code_str
    extract_result, generate_fields = extract_fields_for_extract_and_move_method(refactored_code_str)
    if not extract_result:
        return False, generate_fields, False, generate_fields
    if generate_fields == "no need to refactor.":
        return True, "No refactoring needed.", True, "No refactoring needed."
    target_file_path = generate_fields['target_file_path']
    extracted_method_code = generate_fields['extracted_method_code']
    refactored_method_code = generate_fields['refactored_method_code']
    ## Step 2: Check the target file path exists
    full_target_file_path = os.path.join(project_path, target_file_path)
    checkout_previous_commit(refactoring_object['commitId'], project_path)
    if not os.path.exists(full_target_file_path):
        return False, "The target file path does not exist, please move to an existing java file.", False, "The target file path does not exist, please move to an existing java file."
    ## Step 3: Check the extracted method code and refactored method code
    origin_file_path = os.path.join(project_path, refactoring_object['filePathBefore'])

    try:
        with open(origin_file_path, 'r', encoding='utf-8') as f:
            origin_class_code = f.read()
    except Exception as e:
        return False, f"Failed to read origin file: {e}", False, f"Failed to read origin file: {e}"

    try:
        with open(full_target_file_path, 'r', encoding='utf-8') as f:
            target_class_code = f.read()
    except Exception as e:
        return False, f"Failed to read target file: {e}", False, f"Failed to read target file: {e}"
    # Step 3: Extract the class name and package name
    origin_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)', origin_class_code)
    target_class_match = re.search(r'(?:public\s+)?(?:final\s+|abstract\s+)?(class|interface)\s+(\w+)', target_class_code)
    if not origin_class_match or not target_class_match:
        return False, "Cannot extract class name from origin or target file.", False, "Cannot extract class name from origin or target file."
    target_class_name = target_class_match.group(1)
    target_package_match = re.search(r'package\s+([\w\.]+);', target_class_code)
    target_package = target_package_match.group(1) if target_package_match else ""
    origin_package_match = re.search(r'package\s+([\w\.]+);', origin_class_code)
    origin_package = origin_package_match.group(1) if origin_package_match else ""
    # Step 4: build origin_refactored_code
    origin_refactored_code = origin_class_code.replace(
        refactoring_object['sourceCodeBeforeRefactoring'], refactored_method_code)
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
        return False, "Cannot find closing brace in target class."

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
    compile_re, log = compile_project_for_base(refactoring_object['compileJDK'])
    return check_refactoring_result, message, compile_re, log


def handle_import_in_target_class(extracted_method_code, origin_class_code, target_class_code, origin_package, origin_file_path):
    # 1. 提取普通 import 和 static import
    origin_imports = re.findall(r'import\s+([\w\.]+);', origin_class_code)
    origin_static_imports = re.findall(r'import\s+static\s+([\w\.]+);', origin_class_code)

    target_existing_imports = set(re.findall(r'import\s+([\w\.]+);', target_class_code))
    target_static_imports = set(re.findall(r'import\s+static\s+([\w\.]+);', target_class_code))

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

def check_refactoring_for_single_file(origin_file_path, origin_code, origin_refactored_code, refactoring_type):
    file_path_before = f"{project_prefix_path}/data/tmp/source_code_before_for_whole.txt"
    file_path_after = f"{project_prefix_path}/data/tmp/source_code_after_for_whole.txt"
    with open(file_path_before, "w", encoding="utf-8") as file:
        file.write(origin_code)
    with open(file_path_after, "w", encoding="utf-8") as file:
        file.write(origin_refactored_code)
    return check_refactoring_result_all(refactoring_type, origin_file_path, file_path_before, file_path_after)


def check_refactoring_result_all(refactoring_type, origin_file_path, file_path_before, file_path_after, target_file_path = None):
    global REFACTORING_RESULT
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

def check_refactoring_for_multiple_files(origin_file_path, origin_refactored_code, target_file_path, target_refactored_code, refactoring_type):
    original_refactored_code_path_after = f"{project_prefix_path}/data/tmp/original_refactored_code.txt"
    target_refactored_code_path_after = f"{project_prefix_path}/data/tmp/target_refactored_code.txt"
    with open(original_refactored_code_path_after, "w", encoding="utf-8") as file:
        file.write(origin_refactored_code)
    with open(target_refactored_code_path_after, "w", encoding="utf-8") as file:
        file.write(target_refactored_code)
    return check_refactoring_result_all(refactoring_type, origin_file_path, original_refactored_code_path_after, target_refactored_code_path_after, target_file_path)

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
    method_name_match = re.search(r"public static\s+\w+\s+(\w+)\s*\(", extracted_method_code)
    if method_name_match:
        method_name = method_name_match.group(1)
        if method_name not in refactored_method_code:
            return False, f"Refactored code does not call extracted method '{method_name}'."
    else:
        return False, "Cannot extract method name from extracted method code."

    return True, {
        "target_file_path": target_file_path,
        "extracted_method_code": extracted_method_code,
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
        cleaned_blocks.append(code)
    # Remove empty blocks
    if is_java_code(cleaned_blocks[-1]):
        return cleaned_blocks
    return cleaned_blocks[:-1]  # Exclude the last block which is empty

def is_java_code(code_str):
    # Check if the code string contains Java keywords or syntax
    java_keywords = ['public', 'private', 'protected', 'class', 'interface', 'void', 'int', 'String', 'new', 'return',
                     'System.out']
    score = sum(1 for kw in java_keywords if kw in code_str)

    has_java_style = any(x in code_str for x in [';', '{', '}', '()'])

    return score >= 2 and has_java_style



def check_refactoring_compile_result(refactoring_id: str, refactored_code_str: str):
    print("call check_refactoring_result, refactoring_id:", refactoring_id)
    if refactored_code_str == "":
        return False, "The refactored code is empty.", False, "The refactored code is empty."
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            refactoring_type = refactoring['type']
            if refactoring_type == "Extract Method":
                return check_extract_method_refactoring_compile_result(refactoring_id, refactoring, refactored_code_str)
            if refactoring_type == "Move Method":
                return check_move_method_refactoring_compile_result(refactoring_id, refactoring, refactored_code_str)
            if refactoring_type == "Inline Method":
                return check_inline_method_refactoring_compile_result(refactoring_id, refactoring, refactored_code_str)
            if refactoring_type == "Move And Rename Method":
                return check_move_method_refactoring_compile_result(refactoring_id, refactoring, refactored_code_str)
            if refactoring_type == "Extract And Move Method":
                return check_extract_and_move_method_refactoring_compile_result(refactoring_id, refactoring, refactored_code_str)
            if refactoring_type == "Move And Inline Method":
                return False, "the code didn't perform move and inline method operation.", False, "the code didn't perform move and inline method operation."
    return False, "cannot find the refactoring id", False, "cannot find the refactoring id"


def check_extraction_refactoring(refactoring, refactored_class_code, refactoring_type):
    source_code_before_for_whole = refactoring['sourceCodeBeforeForWhole']
    file_path_before = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/tmp/source_code_before_for_whole.txt"
    file_path_after = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/tmp/source_code_after_for_whole.txt"
    with open(file_path_before, "w", encoding="utf-8") as file:
        file.write(source_code_before_for_whole)
    with open(file_path_after, "w", encoding="utf-8") as file:
        file.write(refactored_class_code)
    java_file_path = refactoring['filePathBefore']
    exe_result = subprocess.run(
        [f"{project_prefix_path}/data/tools/RefactoringMiner-3.0.10/bin/RefactoringMiner", "-scr", java_file_path, file_path_before,
         file_path_after, refactoring_type], capture_output=True, text=True)
    refactoring_result = exe_result.stdout
    last_line = refactoring_result.strip().split('\n')[-1]
    result_word = [word for word in last_line.split()]
    if result_word[0] == "true":
        return True, " the " + refactoring_type + " operation is successful."
    else:
        return False, " the code didn't perform " + refactoring_type + " operation."


def check_move_and_inline_method_refactoring(refactoring, target_file_path):
    if target_file_path == "":
        return False, "the target file path is empty, please move to an existing java file."
    full_file_path = project_path + "/" + target_file_path
    if not os.path.exists(full_file_path):
        return False, " this is a new file, please move to an existing java file."
    with open(full_file_path, "r", encoding="utf-8") as file:
        target_class_code = file.read()
    method_name_before = refactoring['methodNameBefore'].split("#")[1]
    if method_name_before not in target_class_code:
        return False, " the call of move method is not in the target class."
    return True, "the move and inline method operation is successful."


def extract_java_code(agent_answer):
    pattern = re.compile(r'```java(.*?)```', re.DOTALL)
    matches = pattern.findall(agent_answer)
    return "\n".join(matches)


def check_extraction_and_move_method_refactoring(refactoring, refactored_class_code, target_file_path):
    result, message = check_extraction_refactoring(refactoring, refactored_class_code, "Extract Method")
    move_result, move_message = check_move_method_refactoring(target_file_path=target_file_path)
    return result and move_result, message + " " + move_message


def check_move_method_refactoring(target_file_path):
    target_file_path = ""
    if target_file_path == "":
        return False, "the target file path is empty, please move to an existing java file."
    full_file_path = project_path + "/" + target_file_path
    if not os.path.exists(full_file_path):
        return False, " this is a new file, please move to an existing java file."
    return True, "the move method operation is successful."


def get_project_structure_info(refactoring_id: str = "") -> list:
    """Get the project structure information list by refactoring ID."""
    print("call get_project_structure_info, refactoring_id:", refactoring_id)
    if refactoring_id == "":
        return "Please provide the refactoring_id parameter."
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            file_path_before = refactoring['filePathBefore']
            return get_project_structure(project_path, refactoring['commitId'], file_path_before)


def get_prompt_template(refactoring_type):
    if refactoring_type == 'Extract Method':
        prompt_file_path = 'data/prompts/extract_method_baseline_prompt.txt'
        prompt_template = load_prompt_template(prompt_file_path)
        prompt = PromptTemplate(
            input_variables=["task_description", "code_to_refactor", "class_content",
                             "refactoring_operation"],
            template=prompt_template,
        )
        return prompt
    elif refactoring_type == 'Inline Method':
        prompt_file_path = 'data/prompts/inline_method_baseline_prompt.txt'
        prompt_template = load_prompt_template(prompt_file_path)
        prompt = PromptTemplate(
            input_variables=["task_description", "code_to_refactor", "class_content",
                             "refactoring_operation"],
            template=prompt_template,
        )
        return prompt
    elif refactoring_type == 'Move Method':
        prompt_file_path = 'data/prompts/move_method_prompt_baseline.txt'
        prompt_template = load_prompt_template(prompt_file_path)
        prompt = PromptTemplate(
            input_variables=["task_description", "code_to_refactor", "class_content",
                             "refactoring_operation", "project_structure"],
            template=prompt_template,
        )
        return prompt
    elif refactoring_type == 'Move And Rename Method':
        prompt_file_path = 'data/prompts/move_and_rename_method_baseline_prompt.txt'
        prompt_template = load_prompt_template(prompt_file_path)
        prompt = PromptTemplate(
            input_variables=["task_description", "code_to_refactor", "class_content",
                             "refactoring_operation", "project_structure"],
            template=prompt_template,
        )
        return prompt
    elif refactoring_type == 'Extract And Move Method':
        prompt_file_path = 'data/prompts/extract_and_move_method_baseline_prompt.txt'
        prompt_template = load_prompt_template(prompt_file_path)
        prompt = PromptTemplate(
            input_variables=["task_description", "code_to_refactor", "class_content",
                             "refactoring_operation", "project_structure", "file_path_before_refactoring"],
            template=prompt_template,
        )
        return prompt
    elif refactoring_type == 'Move And Inline Method':
        prompt_file_path = 'data/prompts/move_and_inline_baseline_prompt.txt'
        prompt_template = load_prompt_template(prompt_file_path)
        prompt = PromptTemplate(
            input_variables=["task_description", "code_to_refactor", "class_content",
                             "refactoring_operation", "project_structure"],
            template=prompt_template,
        )
        return prompt
    else:
        print("Invalid refactoring type")
        print(refactoring_type)
        return None


# Function to process each commit and refactor the code
def process_commits(output_file_path):
    # 1. 任务介绍
    task_description = """
       You are an expert software engineer. You are given a code to be refactored. The objective is to refactor this code by performing given refactoring operation. This refactoring will improve code readability, maintainability, and modularity.
       """

    # 2. 读取文件路径中的prompt模板

    refactoring_results = []
    for refactoring in tqdm(data):
        try:
            switch_project_path(project_prefix_path)
            source_code_before_refactoring = refactoring['sourceCodeBeforeRefactoring']
            source_code_before_for_whole = refactoring['sourceCodeBeforeForWhole']
            refactoring_operation = refactoring['type']
            prompt = get_prompt_template(refactoring_operation)
            # Generate the final prompt
            if refactoring_operation == 'Extract Method' or refactoring_operation == 'Inline Method':
                final_prompt = prompt.format(
                    task_description=task_description.strip(),
                    code_to_refactor=source_code_before_refactoring.strip(),
                    class_content=source_code_before_for_whole.strip(),
                    refactoring_operation=refactoring_operation.strip()
                )
            elif refactoring_operation == 'Extract And Move Method':
                file_path_before_refactoring = refactoring['filePathBefore']
                project_structure = get_project_structure_info(refactoring['uniqueId'])
                final_prompt = prompt.format(
                    task_description=task_description.strip(),
                    code_to_refactor=source_code_before_refactoring.strip(),
                    class_content=source_code_before_for_whole.strip(),
                    refactoring_operation=refactoring_operation.strip(),
                    project_structure=project_structure,
                    file_path_before_refactoring=file_path_before_refactoring
                )
            else:
                project_structure = get_project_structure_info(refactoring['uniqueId'])
                final_prompt = prompt.format(
                    task_description=task_description.strip(),
                    code_to_refactor=source_code_before_refactoring.strip(),
                    class_content=source_code_before_for_whole.strip(),
                    refactoring_operation=refactoring_operation.strip(),
                    project_structure=project_structure
                )
            print("Prompt: \n$$$$$$$$$$$$$$$$$$$$$$$$\n" + final_prompt + "\n$$$$$$$$$$$$$$$$$$$$$$$$")
            messages = [HumanMessage(content=final_prompt)]
            refactored_code = llm.invoke(messages).content
            print(refactored_code)
            # Check the refactoring result
            refactoring_result, refactoring_message, compile_result, compile_message = check_refactoring_compile_result(refactoring['uniqueId'],
                                                                               refactored_code)
            print(refactoring_message)
            print(compile_message)
            # Collect the result for this commit
            refactoring['refactoringMinerResult'] = refactoring_result
            refactoring['compileAndTestResult'] = compile_result
            refactoring['refactoredCode'] = refactored_code
            refactoring['prompt'] = final_prompt
            refactoring_results.append(refactoring)
        except Exception as e:
            print(f"Error processing refactoring {refactoring['uniqueId']}: {e}")
            continue
    # Save all results to a file
    save_refactoring_results(output_file_path, refactoring_results)


def get_refactoring_ids_from_txt(file_path, start, end):
    refactoring_ids = []
    count = 0
    with open(file_path, 'r') as file:
        for line in file:
            if start <= count < end:
                refactoring_ids.append(line.strip())
            count += 1
    return refactoring_ids

def switch_project_path(local_path):
    try:
        os.chdir(local_path)
        print(f"Switched to project directory: {local_path}")
        return  True, "Switched to directory."
    except Exception as e:
        print(f"Failed to switch to directory {local_path}: {e}")
        return False, f"Failed to switch to directory {local_path} {e}."


if __name__ == "__main__":

    output_file_path = f'{project_prefix_path}/data/{project_name}/{project_name}_baseline_result_{model_name}.json'
    process_commits(output_file_path)

    # Print confirmation
    print(f"Refactored code for all commits saved to {output_file_path}")


