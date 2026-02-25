import json
import os
import re
import subprocess

from util import save_json

# file_path = '/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/refactoring_info/gson_em_pure_refactoring_w_sc_v4_filter.json'
# project_path = '/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/gson'
#
# with open(file_path, 'r') as file:
#     data = json.load(file)

def run_command(command):
    """运行系统命令并捕获输出"""
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    success = result.returncode == 0
    if success:
        print(f"Command succeeded: {command}")
    else:
        print(f"Command failed: {command}\n{result.stderr}")
    return success, result

def checkout_commit(commit_hash):
    """切换到指定的 Git 提交"""
    return run_command(f"git checkout {commit_hash}")


def replace_java_code(file_path, new_code):
    """替换 Java 文件中的代码"""
    try:
        with open(file_path, "w") as file:
            file.write(new_code)
        print(f"Replaced code in {file_path}")
        return True
    except Exception as e:
        print(f"Failed to replace code in {file_path}: {e}")
        return False

def compile_project():
    """编译 Maven 项目"""
    # success, result_first = run_command("mvn clean package -DskipTests=true -Dmaven.test.skip=true")
    # success, result_first = run_command("mvn clean package -Drat.skip=true -Dmaven.javadoc.skip=true")
    # success, result = run_command("./gradlew clean build -x checkstyleMain")
    # success, result_first = run_command("./gradlew clean build -x test  -x spotlessJavaCheck")
    # 
    success, result_first = run_command("./gradlew clean build -x test ")
    if not success:
        success, result = run_command("./gradlew clean build -x test -x checkstyleMain")
    if not success:
        success, result = run_command("./gradlew clean build -x test  -x spotlessJavaCheck")
    if not success:
        success, result = run_command("./gradlew clean build -x test  -x enforceRules")
    if not success:
        success, result = run_command("./gradlew clean build -x test  -x spotlessJava")
    
    str_result = ""
    if not success:
        # 打印构建失败的详细信息
        str_result = "\nBuild failed. Details:\n" + result_first.stdout +result_first.stderr
        ansi_escape = re.compile(r'\x1B\[[0-9;]*[a-zA-Z]')
        str_result = ansi_escape.sub('', str_result)
        str_result = re.findall(r'\[ERROR\].*', str_result)
        print("\nBuild failed. Details:\n")
        print(result_first.stdout)  # 打印标准输出
        print("---------------------------------------------------------------line")
        print(result_first.stderr)  # 打印错误输出
        return success, str_result
    else:
        return success, "Build succeeded."



def force_checkout_commit(commit_id):
    """强制切换到指定的 Git 提交并放弃所有修改"""
    # Step 1: 放弃未提交的修改
    if not run_command("git reset --hard HEAD"):
        print("Failed to discard changes. Exiting.")
        return False

    # Step 2: 切换到指定提交
    if not run_command(f"git checkout -f {commit_id}"):
        print(f"Failed to checkout commit {commit_id}. Exiting.")
        return False

    print(f"Successfully checked out commit {commit_id}.")
    return True

def update_bdn_version(pom_file, new_version="5.1.0", artifact_id="bnd-maven-plugin"):
    try:
        # 读取 pom.xml 文件内容
        with open(pom_file, "r", encoding="utf-8") as file:
            content = file.read()

        # 使用正则表达式匹配 <java.version> 元素并替换其值
        new_content = re.sub(r'<version>4.0.0</version>', f'<version>{new_version}</version>', content)

        # 如果内容有变化，写回文件
        if content != new_content:
            with open(pom_file, "w", encoding="utf-8") as file:
                file.write(new_content)
            print(f"Successfully updated <{artifact_id}> version to {new_version} in {pom_file}")
        else:
            print(f"No changes made. <{artifact_id}> version was already {new_version}.")

    except Exception as e:
        print(f"Error occurred: {e}")

def update_java_version(pom_file, new_version="1.8", new_release="8", bnd_version="5.1.0", artifact_id="bnd-maven-plugin"):
    try:
        # 读取 pom.xml 文件内容
        with open(pom_file, "r", encoding="utf-8") as file:
            content = file.read()

        # 使用正则表达式匹配 <java.version> 元素并替换其值
        new_content = re.sub(r'<java.version>[\d.]+</java.version>', f'<java.version>{new_version}</java.version>',
                             content)
        new_content = re.sub(r'<release>6</release>', f'<release>{new_release}</release>', new_content)

        new_content = re.sub(r'<source>1.5</source>', f'<source>{new_version}</source>', new_content)

        new_content = re.sub(r'<target>1.5</target>', f'<target>{new_version}</target>', new_content)

        new_content = re.sub(r'<source>1.6</source>', f'<source>{new_version}</source>', new_content)

        new_content = re.sub(r'<target>1.6</target>', f'<target>{new_version}</target>', new_content)



        # 如果内容有变化，写回文件
        if content != new_content:
            with open(pom_file, "w", encoding="utf-8") as file:
                file.write(new_content)
            print(f"Successfully updated <java.version> to {new_version} in {pom_file}")
        else:
            print(f"No changes made. <java.version> was already {new_version}.")

    except Exception as e:
        print(f"Error occurred: {e}")

def compile_current_commit(project_dir, commit_id, compile_jdk):

    compile_result = False
    try:
        os.chdir(project_dir)
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
        return compile_result, "Failed to switch to directory."
        # Step 2: 获取指定 commit 的上一个 commit
    force_checkout_commit(commit_id)
    prev_commit = get_previous_commit(commit_id)
    if not prev_commit:
        print("Failed to retrieve previous commit. Exiting.")
        return compile_result, "Failed to retrieve previous commit."

    # Step 3: 切换到上一个 commit
    if not force_checkout_commit(prev_commit):
        print("Failed to checkout previous commit. Exiting.")
        return compile_result, "Failed to checkout previous commit."

    # Step 4: 执行 Maven 构建命令
    print("Running Maven build for the previous commit...")
    # modify_build_file(project_dir)
    switch_java_version(compile_jdk)
    compile_re, log = compile_project()
    switch_java_version(17)
    if not compile_re:
        print("Build failed for the previous commit.")
    else:
        print("Build succeeded for the previous commit.")
        compile_result = True


    ## Step 5: compile current commit
    # print("Running Maven build for the current commit...")
    # if not force_checkout_commit(commit_id):
    #     print("Failed to checkout current commit. Exiting.")
    #     return compile_result, "Failed to checkout current commit."
    # compile_re, log = compile_project()
    # if compile_re:
    #     print("Build succeeded for the current commit.")
    #     compile_result[1] = True
    #     return compile_result, "Build succeeded for the current commit."
    return compile_result, log

def checkout_previous_commit(commit_id, project_dir):
    try:
        os.chdir(project_dir)
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
        return False, "Failed to switch to directory."
        # Step 2: 获取指定 commit 的上一个 commit
    force_checkout_commit(commit_id)
    prev_commit = get_previous_commit(commit_id)
    if not prev_commit:
        print("Failed to retrieve previous commit. Exiting.")
        return False, "Failed to retrieve previous commit."

    # Step 3: 切换到上一个 commit
    if not force_checkout_commit(prev_commit):
        print("Failed to checkout previous commit. Exiting.")
        return False, "Failed to checkout previous commit."

def main(project_dir, commit_id, file_path, new_code):
    compile_result = [False, False, False]
    # Step 1: 切换到指定目录
    try:
        os.chdir(project_dir)
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
        return compile_result, "Failed to switch to directory."
    force_checkout_commit(commit_id)
    # Step 2: 获取指定 commit 的上一个 commit
    prev_commit = get_previous_commit(commit_id)
    if not prev_commit:
        print("Failed to retrieve previous commit. Exiting.")
        return compile_result, "Failed to retrieve previous commit."

    # Step 3: 切换到上一个 commit
    if not force_checkout_commit(prev_commit):
        print("Failed to checkout previous commit. Exiting.")
        return compile_result, "Failed to checkout previous commit."

    # # Step 4: 执行 Maven 构建命令
    # print("Running Maven build for the previous commit...")
    # compile_re, log = compile_project()
    # if not compile_re:
    #     print("Build failed for the previous commit.")
    #     compile_result[0] = True
    #     compile_result[1] = True
    #     compile_result[2] = True
    #     return compile_result, "Build failed for the previous commit."
    # else:
    #     print("Build succeeded for the previous commit.")
    compile_result[0] = True

    # Step 5: 替换 Java 文件中的代码
    print(f"Replacing code in {file_path}...")
    if not replace_java_code(file_path, new_code):
        print("Failed to replace code. Exiting.")
        return compile_result, "Failed to replace code."

    compile_result[1] = True
    # modify_build_file(project_dir)
    # Step 6: 再次执行 Maven 构建命令
    print("Running Maven build after code replacement...")
    compile_result_after_replacement, log = compile_project()
    if compile_result_after_replacement:
        print("Build succeeded after code replacement.")
        compile_result[2] = True
        return compile_result, "Build succeeded after code replacement."
    else:
        print("Build failed after code replacement.")
        return compile_result, log

def compile_for_move_operation(project_dir, commit_id, original_file_path, original_refactored_code, target_file_path, target_refactored_code):
    compile_result = [False, False, False]
    # Step 1: 切换到指定目录
    try:
        os.chdir(project_dir)
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
        return compile_result, "Failed to switch to directory."
    force_checkout_commit(commit_id)
    # Step 2: 获取指定 commit 的上一个 commit
    prev_commit = get_previous_commit(commit_id)
    if not prev_commit:
        print("Failed to retrieve previous commit. Exiting.")
        return compile_result, "Failed to retrieve previous commit."

    # Step 3: 切换到上一个 commit
    if not force_checkout_commit(prev_commit):
        print("Failed to checkout previous commit. Exiting.")
        return compile_result, "Failed to checkout previous commit."

    # # Step 4: 执行 Maven 构建命令
    # print("Running Maven build for the previous commit...")
    # compile_re, log = compile_project()
    # if not compile_re:
    #     print("Build failed for the previous commit.")
    #     return compile_result, "Build failed for the previous commit."
    # else:
    #     print("Build succeeded for the previous commit.")
    compile_result[0] = True

    # Step 5: 替换 Java 文件中的代码
    if not replace_java_code(original_file_path, original_refactored_code):
        print("Failed to replace code. Exiting.")
        return compile_result, "Failed to replace code."

    if not replace_java_code(target_file_path, target_refactored_code):
        print("Failed to replace code. Exiting.")
        return compile_result, "Failed to replace code."

    compile_result[1] = True
    # Step 6: 再次执行 Maven 构建命令
    print("Running Maven build after code replacement...")
    compile_result_after_replacement, log = compile_project()
    if compile_result_after_replacement:
        print("Build succeeded after code replacement.")
        compile_result[2] = True
        return compile_result, "Build succeeded after code replacement."
    else:
        print("Build failed after code replacement.")
        return compile_result, log

def update_config_for_jenv():
    # 定义要添加到 .bashrc 的内容
    bashrc_content = """
    export PATH="$HOME/.jenv/bin:$PATH"
    eval "$(jenv init -)"
    """

    # 获取当前用户的主目录
    home_dir = os.path.expanduser("~")

    # 构建 .bashrc 路径
    bashrc_path = os.path.join(home_dir, '.bashrc')

    # 打开并追加内容到 .bashrc
    with open(bashrc_path, 'a') as bashrc_file:
        bashrc_file.write(bashrc_content)

    # 执行 source ~/.bashrc 命令
    subprocess.run(['source', bashrc_path], shell=True, executable='/bin/bash')

    print("配置已更新并执行 source ~/.bashrc")

def switch_java_version(version):
    """
    通过命令行切换 Java 版本。

    :param version: 要切换的 Java 版本（如 '17' 或 '11'）。
    :return: None
    """
    try:
        # 构建 jenv 切换命令

        command = ["jenv", "local", str(version)]

        # 执行命令
        subprocess.run(command, check=True)

        # 检查是否切换成功
        result = subprocess.run(["jenv", "version"], capture_output=True, text=True, check=True)
        if str(version) in result.stdout:
            print(f"成功切换到 Java {version}。")
        else:
            print(f"切换到 Java {version} 失败。当前版本: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"切换 Java 版本失败: {e}")
    except FileNotFoundError:
        print("未找到 jenv 命令，请确保 jenv 已正确安装并在路径中。")

def get_compile_result_for_extract_method(project_dir, commit_id, file_path, refactored_code, java_version = 11):

    switch_java_version(java_version)
    compile_result, log = main(project_dir, commit_id, file_path, refactored_code)
    switch_java_version(17)
    try:
        os.chdir("/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring")
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
    if compile_result[0] and compile_result[1] and compile_result[2]:
        return True, "This commit can be compile and test successfully."
    if compile_result[0] and compile_result[1]:
        return False, log
    if not compile_result[0]:
        raise Exception("Failed to compile the previous commit.")


def get_compile_result_in_commit(project_dir, commit_id, file_path, refactored_code, java_version = 11):
    switch_java_version(java_version)
    compile_result, log = main(project_dir, commit_id, file_path, refactored_code)
    switch_java_version(17)
    try:
        os.chdir("/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring")
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
    if compile_result[0] and compile_result[1] and compile_result[2]:
        return True, "This commit can be compile and test successfully."
    if compile_result[0] and compile_result[1]:
        return False, log
    if not compile_result[0]:
        raise Exception("Failed to compile the previous commit.")

def get_compile_result_move_operation(project_dir, commit_id, superclass_file_path, superclass_refactored_code, subclass_file_path, subclass_refactored_code, java_version = 11):
    switch_java_version(java_version)
    compile_result, log = compile_for_move_operation(project_dir, commit_id, superclass_file_path, superclass_refactored_code, subclass_file_path, subclass_refactored_code)
    switch_java_version(17)
    try:
        os.chdir("/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring")
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
    if compile_result[0] and compile_result[1] and compile_result[2]:
        return True, "This commit can be compile and test successfully."
    if compile_result[0] and compile_result[1]:
        return False, log
    if not compile_result[0]:
        raise Exception("Failed to compile the previous commit.")


def get_previous_commit(commit_id):
    """获取指定 commit 的上一个 commit"""
    result = subprocess.run(f"git rev-parse {commit_id}~1", shell=True, text=True, capture_output=True)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        print(f"Failed to get the previous commit for {commit_id}: {result.stderr}")
        return None

def get_whole_refactored_code_after_refactoring(refactoring_id: str):
    """
    Get the refactored code after refactoring by refactoring ID.
    """
    print("call get_refactored_code_after_refactoring, refactoring_id: ", refactoring_id)
    # commits = data['commits']
    commits = []
    commits.reverse()
    for commit in commits:
        if "refactoringAnalyses" not in commit:
            continue
        for refactoring in commit['refactoringAnalyses']:
            if refactoring['uniqueId'] == refactoring_id:
                return refactoring

def process_experiment_result(result_file_path, start_index=0, end_index=100):
    with open(result_file_path, 'r') as file:
        data = json.load(file)
    count = 0
    compile_and_test_data = []
    for refactoring in data:
        if  start_index <= count < end_index:
            if "refactoredCode" in refactoring and refactoring['refactoredCode']:
                refactoring_result = get_whole_refactored_code_after_refactoring(refactoring['uniqueId'])
                compile_and_test_data.append({
                    'commitUrl': "https://github.com/google/gson/commit/" + refactoring_result['commitId'],
                    'filePath': refactoring_result['filePathBefore'],
                    'agentRefactoredCode': extract_java_code(refactoring['refactoredCode']),
                    'sourceCodeBeforeRefactoring': refactoring_result['sourceCodeBeforeRefactoring'],
                    'methodNameBefore': refactoring_result['methodNameBefore'],
                    'commitId': refactoring_result['commitId'],
                    'sourceCodeBeforeForWhole': refactoring_result['sourceCodeBeforeForWhole'],
                    'sourceCodeAfterRefactoring': refactoring_result['sourceCodeAfterRefactoring'],
                    'type': refactoring_result['type'],
                    'sourceCodeAfterForWhole': refactoring_result['sourceCodeAfterForWhole']
                })
            else:
                chat_logs = refactoring["agentChatLog"]
                chat_logs.reverse()
                for chat_log in chat_logs:
                    java_code = extract_java_code(chat_log)
                    if java_code:
                        compile_and_test_data.append({
                            'commitUrl': "https://github.com/google/gson/commit/" + refactoring['commitId'],
                            'filePath': refactoring['filePathBefore'],
                            'agentRefactoredCode': java_code,
                            'sourceCodeBeforeRefactoring': refactoring['sourceCodeBeforeRefactoring'],
                            'methodNameBefore': refactoring['methodNameBefore'],
                            'commitId': refactoring['commitId'],
                            'sourceCodeBeforeForWhole': refactoring['sourceCodeBeforeForWhole'],
                            'sourceCodeAfterRefactoring': refactoring['sourceCodeAfterRefactoring'],
                            'type': refactoring['type'],
                            'sourceCodeAfterForWhole': refactoring['sourceCodeAfterForWhole']
                        })
                        break
        count += 1
    return compile_and_test_data



def extract_java_code(agent_answer):
    pattern = re.compile(r'```java(.*?)```', re.DOTALL)
    matches = pattern.findall(agent_answer)
    return "\n".join(matches)

def get_commit_time(commit_id):
    result = subprocess.run(f"git show -s --format=%ci {commit_id}", shell=True, text=True, capture_output=True)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        print(f"Failed to get the commit time for {commit_id}: {result.stderr}")
        return None




def check_baseline_refactoring_result():
    output_file_path = "data/refactored_code/baseline/gson_em_refactoring_agent_baseline_result_11_30_40-43.json"
    file_path_list =['data/output/gson_em_pure_refactoring_baseline_filter_v6_40-43.json',]
    project_dir = "/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/gson"
    compile_result_file_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/refactored_code/baseline/gson_em_refactoring_agent_baseline_result_11_30_40-43_compile_result.json"
    process_result = []
    for file_path in file_path_list:
         result = process_experiment_result(file_path, 0, 3)
         process_result.extend(result)
    save_json(output_file_path, process_result)
    switch_java_version(1.8)
    for refactoring in process_result:
        commit_id = refactoring['commitId']
        file_path = project_dir + '/' + refactoring['filePath']
        compile_result, log = main(project_dir, commit_id, file_path, refactoring['agentRefactoredCode'])
        refactoring['compileResult'] = compile_result
    switch_java_version(17)
    save_json(compile_result_file_path, process_result)

def get_ast_accuracy(source_code_before_for_whole, refactored_class_code):
    file_path_before = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/file_path_before"
    java_file_path_before = file_path_before + "/Example.java"
    file_path_after = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/file_path_after"
    java_file_path_after = file_path_after + "/Example.java"
    with open(java_file_path_before, "w", encoding="utf-8") as file:
        file.write(source_code_before_for_whole)
    with open(java_file_path_after, "w", encoding="utf-8") as file:
        file.write(refactored_class_code)
    exe_result = subprocess.run(
        ["./data/tools/RefactoringMiner-3.0.9/bin/RefactoringMiner", "-ast", file_path_before, file_path_after], capture_output=True, text=True)
    refactoring_result = exe_result.stdout
    last_line = refactoring_result.strip().split('\n')[-1]
    return last_line

def count_ast_accuracy_for_base_line():
    with open("data/refactored_code/baseline/gson_em_refactoring_agent_baseline_result_11_30_40-43_compile_result.json", 'r') as file:
        data = json.load(file)

    for refactoring in data:
        if refactoring['type'] == "Extract Method" and all(refactoring['compileResult']):
            source_code_before = refactoring['sourceCodeAfterForWhole']
            refactored_code = refactoring['agentRefactoredCode']
            ast_accuracy = get_ast_accuracy(source_code_before, refactored_code)
            refactoring['astAccuracy'] = ast_accuracy
    save_json("data/refactored_code/baseline/gson_em_refactoring_agent_baseline_result_40_43_ast_accuracy.json", data)

def count_ast_accuracy_for_our_approach():
    with open("data/refactored_code/MUARF/gson_em_refactoring_agent_result_11_20.json", 'r') as file:
        data = json.load(file)
    ast_refactoring_result = []
    for refactoring in data:
        if refactoring['type'] != "Move Method" and refactoring["refactoringResult"] and refactoring['type'] != "Move And Rename Method":
            source_code_before = refactoring['sourceCodeAfterForWhole']
            refactored_code = refactoring['agentRefactoredCode']
            ast_accuracy = get_ast_accuracy(source_code_before, refactored_code)
            refactoring['astAccuracy'] = ast_accuracy
        ast_refactoring_result.append(refactoring)

    save_json("data/refactored_code/MUARF/gson_em_refactoring_agent_result_11_20_ast_accuracy.json", ast_refactoring_result)

def process_muarf_refactoring_result():
    refactoring_result_file_path_list = ["data/output/gson_em_refactoring_agent_result_11_27_0-14-20.json",
                                         "data/output/gson_em_refactoring_agent_result_11_27_0-20-30.json",
                                         "data/output/gson_em_refactoring_agent_result_11_27_0-35-43.json"]
    compile_result_file_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/refactored_code/MUARF/gson_em_refactoring_agent_result_14_43_compile_result.json"
    process_result = []
    for refactoring_result_file_path in refactoring_result_file_path_list:
        result = process_experiment_result(refactoring_result_file_path, 0, 100)
        process_result.extend(result)
    save_json(compile_result_file_path, process_result)

def process_without_rag_refactoring_result():
    refactoring_result_file_path_list = ["data/output/gson_em_refactoring_agent_without_rag_result_11_27_0-10.json",
                                         "data/output/gson_em_refactoring_agent_without_rag_result_11_27_10-20.json",
                                         "data/output/gson_em_refactoring_agent_without_rag_result_11_27_20-30.json",
                                         "data/output/gson_em_refactoring_agent_without_rag_result_11_27_35-42.json",
                                         "data/output/gson_em_refactoring_agent_without_rag_result_11_27_42-43.json"]
    compile_result_file_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/refactored_code/without_rag/gson_em_refactoring_without_rag_for_compile.json"
    process_result = []
    for refactoring_result_file_path in refactoring_result_file_path_list:
        result = process_experiment_result(refactoring_result_file_path, 0, 100)
        process_result.extend(result)
    save_json(compile_result_file_path, process_result)

def count_ast_accuracy_for_without_rag():
    with open("data/refactored_code/without_rag/gson_em_refactoring_without_rag_for_compile.json", 'r') as file:
        data = json.load(file)
    ast_refactoring_result = []
    for refactoring in data:
        if refactoring['type'] != "Move Method" and refactoring["refactoringResult"] and refactoring['type'] != "Move And Rename Method":
            source_code_before = refactoring['sourceCodeAfterForWhole']
            refactored_code = refactoring['agentRefactoredCode']
            ast_accuracy = get_ast_accuracy(source_code_before, refactored_code)
            refactoring['astAccuracy'] = ast_accuracy
        ast_refactoring_result.append(refactoring)

    save_json("data/refactored_code/without_rag/gson_em_refactoring_without_rag_ast_accuracy.json", ast_refactoring_result)

def count_ast_accuracy_for_without_ref():
    with open("data/refactored_code/without_rfm/gson_em_refactoring_without_refactoring_miner_for_compile.json", 'r') as file:
        data = json.load(file)
    ast_refactoring_result = []
    for refactoring in data:
        if refactoring['type'] != "Move Method" and all(refactoring["refactoringMinerResult"]) and refactoring['type'] != "Move And Rename Method":
            source_code_before = refactoring['sourceCodeAfterForWhole']
            refactored_code = refactoring['agentRefactoredCode']
            ast_accuracy = get_ast_accuracy(source_code_before, refactored_code)
            refactoring['astAccuracy'] = ast_accuracy
        ast_refactoring_result.append(refactoring)

    save_json("data/refactored_code/without_rfm/gson_em_refactoring_without_rfm_ast_accuracy.json", ast_refactoring_result)

def count_ast_accuracy_for_without_agents():
    with open("data/refactored_code/without_agents/gson_em_refactoring_without_agents_for_compile_35-43.json", 'r') as file:
        data = json.load(file)
    ast_refactoring_result = []
    for refactoring in data:
        if refactoring['type'] != "Move Method" and all(refactoring["refactoringMinerResult"]) and refactoring['type'] != "Move And Rename Method" and all(refactoring["compileResult"]):
            source_code_before = refactoring['sourceCodeAfterForWhole']
            refactored_code = refactoring['agentRefactoredCode']
            ast_accuracy = get_ast_accuracy(source_code_before, refactored_code)
            refactoring['astAccuracy'] = ast_accuracy
        ast_refactoring_result.append(refactoring)

    save_json("data/refactored_code/without_agents/gson_em_refactoring_without_agents_ast_accuracy_35-43.json", ast_refactoring_result)

def get_refactoring_miner_result():
    refactoring_result_file_path_list = ["data/output/gson_em_refactoring_agent_result_without_refactoring_miner_11_27_0-0-10.json",
                                         "data/output/gson_em_refactoring_agent_result_without_refactoring_miner_11_27_0-10-20.json",
                                         "data/output/gson_em_refactoring_agent_result_without_refactoring_miner_11_27_0-20-30.json",
                                         "data/output/gson_em_refactoring_agent_result_without_refactoring_miner_11_27_0-35-43.json"]
    compile_result_file_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/refactored_code/without_rfm/gson_em_refactoring_without_refactoring_miner_for_compile.json"
    process_result = []
    for refactoring_result_file_path in refactoring_result_file_path_list:
        result = process_experiment_result(refactoring_result_file_path, 0, 100)
        process_result.extend(result)
    save_json(compile_result_file_path, process_result)

    for refactoring in process_result:
        source_code_before_for_whole = refactoring['sourceCodeBeforeForWhole']
        refactored_class_code = refactoring['agentRefactoredCode']
        refactoring_type = refactoring['type']
        file_path_before = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/tmp/source_code_before_for_whole.txt"
        file_path_after = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/tmp/source_code_after_for_whole.txt"
        with open(file_path_before, "w", encoding="utf-8") as file:
            file.write(source_code_before_for_whole)
        with open(file_path_after, "w", encoding="utf-8") as file:
            file.write(refactored_class_code)
        java_file_path = refactoring['filePath']
        exe_result = subprocess.run(
            ["./data/tools/RefactoringMiner-3.0.9/bin/RefactoringMiner", "-scr", java_file_path, file_path_before,
             file_path_after, refactoring_type], capture_output=True, text=True)
        refactoring_result = exe_result.stdout
        last_line = refactoring_result.strip().split('\n')[-1]
        result_word = [word for word in last_line.split()]
        refactoring['refactoringMinerResult'] = result_word
    save_json(compile_result_file_path, process_result)

def get_result_without_agent_workflow():
    refactoring_result_file_path_list = [
        "data/output/gson_em_refactoring_without_agent_result_11_27_0-35-43.json"]
    compile_result_file_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/refactored_code/without_agents/gson_em_refactoring_without_agents_for_compile_35-43.json"
    process_result = []
    for refactoring_result_file_path in refactoring_result_file_path_list:
        result = process_experiment_result(refactoring_result_file_path, 0, 100)
        process_result.extend(result)
    save_json(compile_result_file_path, process_result)

    for refactoring in process_result:
        source_code_before_for_whole = refactoring['sourceCodeBeforeForWhole']
        refactored_class_code = refactoring['agentRefactoredCode']
        refactoring_type = refactoring['type']
        file_path_before = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/tmp/source_code_before_for_whole.txt"
        file_path_after = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/tmp/source_code_after_for_whole.txt"
        with open(file_path_before, "w", encoding="utf-8") as file:
            file.write(source_code_before_for_whole)
        with open(file_path_after, "w", encoding="utf-8") as file:
            file.write(refactored_class_code)
        java_file_path = refactoring['filePath']
        exe_result = subprocess.run(
            ["./data/tools/RefactoringMiner-3.0.9/bin/RefactoringMiner", "-scr", java_file_path, file_path_before,
             file_path_after, refactoring_type], capture_output=True, text=True)
        refactoring_result = exe_result.stdout
        last_line = refactoring_result.strip().split('\n')[-1]
        result_word = [word for word in last_line.split()]
        refactoring['refactoringMinerResult'] = result_word
    save_json(compile_result_file_path, process_result)
    project_dir = "/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/gson"
    switch_java_version(1.8)
    for refactoring in process_result:
        commit_id = refactoring['commitId']
        file_path = project_dir + '/' + refactoring['filePath']
        compile_result, log = main(project_dir, commit_id, file_path, refactoring['agentRefactoredCode'])
        refactoring['compileResult'] = compile_result
    switch_java_version(17)
    save_json(compile_result_file_path, process_result)

if __name__ == "__main__":
    count_ast_accuracy_for_without_agents()
    # 示例参数
    # result_file_path = "data/output/gson_em_refactoring_agent_result_11_18_without_rag_10-30.json"
    # output_file_path = "data/refactored_code/baseline/gson_em_refactoring_agent_baseline_result_11_20.json"
    # project_dir = "/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/gson"
    # compile_result_file_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/output/gson_test_result_em_assist_2.json"
    # file_path_list =['data/output/gson_test_result_baseline_0-20.json',]
    # process_result = []
    # for file_path in file_path_list:
    #     result = process_experiment_result(file_path)
    #     process_result.extend(result)
    # # # process_result = process_experiment_result(result_file_path)
    # save_json(output_file_path, process_result)

    # output_file_path = "data/output/gson_em_pure_refactoring_baseline_filter_v5.json"
    # with open(output_file_path, 'r') as file:
    #     data = json.load(file)
    # with open('data/refactoring_info/sourceCodeAfter1.txt', 'r') as file:
    #     file_contents = file.read()
    # source_code_after = file_contents
    # for refactoring in data:
    #     commit_id = refactoring['commitId']
    #     if refactoring['uniqueId'] == 'a0dc7bfdddfe488510edde8d8abb0727743394c4_250_276_379_382_330_357':
    #         compile_result, log = main(project_dir, commit_id, refactoring['filePathBefore'], source_code_after)
    #         refactoring['compileResult'] = compile_result
    #         break
    #     # file_path = project_dir + '/' + refactoring['filePathBefore']
    #     # refactored_code = extract_java_code(refactoring['refactoredCode'])
    # save_json(compile_result_file_path, data)