import json
import os

from compile_experiment import get_previous_commit, get_commit_time
from handle_excel import ExcelUtil
from jacoco_util import get_jacoco_result, extract_method_coverage, is_test_method
from util.project_util import get_project_structure


def filter_pure_refactoring(project_name, skip_commit_file):
    """ Filter out refactoring analyses that are not pure refactorings """
    file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_refactoring_info.json'
    output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info.json'
    with open(file_path, 'r') as file:
        data = json.load(file)
    with open(skip_commit_file, 'r') as file:
        skip_commit_list = file.readlines()
    unique_ids_set = set()  # 用于存储已经添加的 uniqueId
    pure_refactoring_list = []
    # 遍历 JSON 中的 commits
    for commit in data['commits']:
        if "refactoringAnalyses" not in commit:
            continue
        if commit['commitId'] in skip_commit_list:
            print(f"Skipping commit: {commit['commitId']}")
            continue
        filter_refactoring_list = []
        for refactoring in commit['refactoringAnalyses']:
            unique_id = refactoring['uniqueId']
            # 检查是否已经存在该 uniqueId
            if unique_id not in unique_ids_set and refactoring['isPureRefactoring']:
               filter_refactoring_list.append(refactoring)
               unique_ids_set.add(unique_id)
            else:
                if unique_id in unique_ids_set:
                    print(f"Skipping duplicate uniqueId: {unique_id}")
        if filter_refactoring_list :
            pure_refactoring_list.extend(filter_refactoring_list)
    with open(output_file_path, 'w') as file:
        json.dump(pure_refactoring_list, file, indent=4)

def filter_compiled_and_test_commits(project_name):
    """ filter commits that can be compiled successfully """
    data_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_result.json'
    project_dir = f'/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/{project_name}'
    output_excel_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_compile_result_before_refactoring.xlsx'
    data_output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_and_test_result.json'
    with open(data_file_path, 'r') as file:
        data = json.load(file)
    try:
        os.chdir(project_dir)
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
        return
    data.reverse()
    excel_util = ExcelUtil(output_excel_path)
    construct_excel_for_compile_filter(data, excel_util, project_dir, "jdk_17", 17)
    construct_excel_for_compile_filter(data, excel_util, project_dir, "jdk_11", 11)
    construct_excel_for_compile_filter(data, excel_util, project_dir, "jdk_1.8", 1.8)
    # construct_excel_for_compile_filter(data, excel_util, project_dir, "jdk_21", 21)

    excel_util.save()
    with open(data_output_file_path, 'w') as file:
        json.dump(data, file, indent=4)

def filter_commits_with_test_cases(project_name):
    """ filter commits that have test cases """
    project_dir = f"/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/{project_name}"
    data_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_result.json'
    data_output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_and_test_result.json'
    pom_file = "./pom.xml"
    with open(data_file_path, 'r') as file:
        data = json.load(file)

    for refactoring in data:
        commit_hash = refactoring['commitId']
        class_name = refactoring['classNameBefore']
        class_file = refactoring['filePathBefore']
        method_name = refactoring['methodNameBefore'].split("#")[1]
        compile_result_before = refactoring["compileResultBefore"]
        compile_jdk = refactoring["compileJDK"]
        if "testResult" in refactoring and refactoring["testResult"]:
            continue
        if not compile_result_before:
            refactoring["testResult"] = False
            refactoring["coverageInfo"] = {"Compile Failure": {"missed": 0, "covered": 0}}
        else:
            coverage_result, info = get_jacoco_result(project_dir, commit_hash, class_name, method_name, class_file, pom_file, compile_jdk)
            refactoring["testResult"] = coverage_result
            refactoring["coverageInfo"] = info

    with open(data_output_file_path, 'w') as file:
        json.dump(data, file, indent=4)

def filter_commits_with_test_cases_with_commit_id(project_name, unique_id):
    """ filter commits that have test cases """
    project_dir = f"/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/{project_name}"
    data_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_result.json'
    data_output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_and_test_result.json'
    pom_file = "./pom.xml"
    with open(data_file_path, 'r') as file:
        data = json.load(file)

    commit_id_set = set()
    for refactoring in data:
        commit_hash = refactoring['commitId']
        class_name = refactoring['classNameBefore']
        class_file = refactoring['filePathBefore']
        method_name = refactoring['methodNameBefore'].split("#")[1]
        compile_result_before = refactoring["compileResultBefore"]
        compile_jdk = refactoring["compileJDK"]
        if unique_id == refactoring['uniqueId']:
            coverage_result, info = get_jacoco_result(project_dir, commit_hash, class_name, method_name, class_file,
                                                      pom_file, compile_jdk, commit_id_set)
            refactoring["testResult"] = coverage_result
            refactoring["coverageInfo"] = info
            print(f"uniqueId: {unique_id}, testResult: {coverage_result}")


def generate_data_for_evaluation(project_name):
    """ generate data for evaluation """
    data_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_and_test_result.json'
    output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_evaluation_data.json'
    with open(data_file_path, 'r') as file:
        data = json.load(file)
    evaluation_data = []
    for refactoring in data:
        if refactoring["compileResultBefore"] and refactoring["testResult"] and refactoring["moveFileExist"]:
            evaluation_data.append(refactoring)
    with open(output_file_path, 'w') as file:
        json.dump(evaluation_data, file, indent=4)


def construct_excel_for_compile_filter(data, excel_util, project_dir, jdk_, java_version_before):
    excel_util.create_sheet(jdk_)
    excel_util.write_cell(jdk_, 1, 1, "currentCommitId")
    excel_util.write_cell(jdk_, 1, 2, "currentCommitTime")
    excel_util.write_cell(jdk_, 1, 3, "parentCommitId")
    excel_util.write_cell(jdk_, 1, 4, "parentCommitTime")
    excel_util.write_cell(jdk_, 1, 5, "refactoringType")
    excel_util.write_cell(jdk_, 1, 6, "methodNameBefore")
    excel_util.write_cell(jdk_, 1, 7, "currentCommitCompileResult")
    excel_util.write_cell(jdk_, 1, 8, "parentCommitCompileResult")
    count = 2
    commit_id_map = {}
    project_dir = f"/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/{project_name}"
    pom_file = "./pom.xml"
    for refactoring in data:
        move_class_exist = refactoring["moveFileExist"]
        current_commit_id = refactoring['commitId']
        parent_commit_id = get_previous_commit(current_commit_id)
        current_commit_time = get_commit_time(current_commit_id)
        parent_commit_time = get_commit_time(parent_commit_id)
        refactoring_type = refactoring['type']
        method_name_before = refactoring['methodNameBefore']
        class_file = refactoring['filePathBefore']
        class_name = refactoring['classNameBefore']
        method_name = refactoring['methodNameBefore'].split("#")[1]
        compile_java_version = java_version_before
        if move_class_exist:
            if commit_id_map.get(refactoring['commitId']):
                print(f"refactoring exist: {refactoring['commitId']}")
                compile_result_json = commit_id_map[current_commit_id]
                parent_commit_compile_result = compile_result_json["parentCommitCompileResult"]
                current_commit_compile_result = compile_result_json["currentCommitCompileResult"]
                compile_java_version = compile_result_json["compileJDK"]
                refactoring["compileResultBefore"] = parent_commit_compile_result
                refactoring["compileResultCurrent"] = current_commit_compile_result
                refactoring["compileJDK"] = compile_java_version
                if refactoring["compileResultBefore"]:
                    try:
                        os.chdir(project_dir)
                        print(f"Switched to project directory: {project_dir}")
                    except Exception as e:
                        print(f"Failed to switch to directory {project_dir}: {e}")
                        return
                    if not is_test_method(class_file):
                        coverage = extract_method_coverage(class_name, method_name, class_file)
                        # Step 5: 提取覆盖率信息
                        if coverage:
                            if coverage[method_name]["LINE"]["covered"] != 0:
                                refactoring["testResult"] = True
                                refactoring["coverageInfo"] = coverage[method_name]
                            else:
                                refactoring["testResult"] = False
                                refactoring["coverageInfo"] = coverage[method_name]
                        else:
                            print(f"Coverage information not found for {class_name}.{method_name}")
                            refactoring["testResult"] = False
                            refactoring["coverageInfo"] = {"Can't Find Information": {"missed": 0, "covered": 0}}
                    else:
                        print(f"The method {method_name} is a test method; skipping coverage extraction.")
                        refactoring["testResult"] = True
                        refactoring["coverageInfo"] = {"testMethod": {"missed": 0, "covered": 1}}
            else:
                if "compileResultBefore" in refactoring and refactoring["compileResultBefore"]:
                    print("before compile result exist")
                    parent_commit_compile_result = refactoring["compileResultBefore"]
                    current_commit_compile_result = refactoring["compileResultCurrent"]
                    compile_java_version = refactoring["compileJDK"]
                else:
                    compile_result, coverage_result, info = get_jacoco_result(project_dir, current_commit_id, refactoring['classNameBefore'], refactoring['methodNameBefore'].split("#")[1], refactoring['filePathBefore'], pom_file, compile_java_version)
                    # compile_result, log = compile_current_commit(project_dir, current_commit_id)
                    current_commit_compile_result = compile_result
                    parent_commit_compile_result = compile_result
                    refactoring["testResult"] = coverage_result
                    refactoring["coverageInfo"] = info
        else:
            parent_commit_compile_result = False
            current_commit_compile_result = False
            refactoring["testResult"] = False
            refactoring["coverageInfo"] = {"Move File Not Exist": {"missed": 0, "covered": 0}}
            compile_result_json = {
                "parentCommitCompileResult": parent_commit_compile_result,
                "currentCommitCompileResult": current_commit_compile_result,
                "compileJDK": compile_java_version
            }
            commit_id_map[refactoring['commitId']] = compile_result_json
        refactoring["compileResultBefore"] = parent_commit_compile_result
        refactoring["compileResultCurrent"] = current_commit_compile_result
        refactoring["compileJDK"] = compile_java_version
        excel_util.write_cell(jdk_, count, 1, current_commit_id)
        excel_util.write_cell(jdk_, count, 2, current_commit_time)
        excel_util.write_cell(jdk_, count, 3, parent_commit_id)
        excel_util.write_cell(jdk_, count, 4, parent_commit_time)
        excel_util.write_cell(jdk_, count, 5, refactoring_type)
        excel_util.write_cell(jdk_, count, 6, method_name_before)
        excel_util.write_cell(jdk_, count, 7, current_commit_compile_result)
        excel_util.write_cell(jdk_, count, 8, parent_commit_compile_result)
        count += 1

def make_sure_move_method_target_class(project_name):
    data_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info.json'
    # data_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_with_compile_and_test_result.json'
    project_dir = f'/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/{project_name}'
    data_output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_result.json'
    with open(data_file_path, 'r') as file:
        data = json.load(file)
    for refactoring in data:
        if refactoring["type"] == "Move Method" or refactoring["type"] == "Move And Rename Method" or refactoring["type"] == "Move And Inline Method":
            commit_id = refactoring["commitId"]
            file_path_before_refactoring = refactoring["filePathBefore"]
            project_structure = get_project_structure(project_dir, commit_id, file_path_before_refactoring)
            file_path_after_refactoring = refactoring["filePathAfter"]
            if file_path_after_refactoring not in project_structure:
                refactoring["moveFileExist"] = False
            else:
                refactoring["moveFileExist"] = True
        else:
            refactoring["moveFileExist"] = True
    with open(data_output_file_path, 'w') as file:
        json.dump(data, file, indent=4)

def merge_two_datasets(project_name):
    data_file_path_1 = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_and_test_result.json'
    data_file_path_2 = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_2.json'
    data_output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_pure_refactoring_info_move_with_compile_and_test_result_2.json'
    with open(data_file_path_1, 'r') as file:
        data_1 = json.load(file)
    with open(data_file_path_2, 'r') as file:
        data_2 = json.load(file)
    for refactoring_1 in data_1:
        for refactoring_2 in data_2:
            if refactoring_1["uniqueId"] == refactoring_2["uniqueId"]:
                refactoring_1["methodNameBefore"] = refactoring_2["methodNameBefore"]
                refactoring_1["methodNameBeforeSet"] = refactoring_2["methodNameBeforeSet"]

    with open(data_output_file_path, 'w') as file:
        json.dump(data_1, file, indent=4)

def merge_datasets(project_name):
    data_file_path_1 = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_em_pure_refactoring_w_sc_v6_1.json'
    data_file_path_2 = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_em_pure_refactoring_w_sc_v6_2.json'
    # data_file_path_3 = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_em_pure_refactoring_w_sc_v6_2024.json'
    data_output_file_path = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_refactoring_info.json'
    with open(data_file_path_1, 'r') as file:
        data_1 = json.load(file)
    with open(data_file_path_2, 'r') as file:
        data_2 = json.load(file)
    # with open(data_file_path_3, 'r') as file:
    #     data_3 = json.load(file)
    for commit in data_2['commits']:
        data_1['commits'].append(commit)
    # for commit in data_3['commits']:
    #     data_1['commits'].append(commit)
    with open(data_output_file_path, 'w') as file:
        json.dump(data_1, file, indent=4)

def pre_process_data(project_name, skip_commit_file):
    # 0. merge datasets
    # merge_datasets(project_name)
    print("0. merge datasets done")
    # 1. 预处理数据，提取出只有pure refactoring的commit
    filter_pure_refactoring(project_name, skip_commit_file)
    print("1. filter pure refactoring done")
    # 2. Move Method的target class 确保存在
    make_sure_move_method_target_class(project_name)
    print("2. make sure move method target class done")
    # # 3. 编译测试，提取出只能编译成功的commit
    filter_compiled_and_test_commits(project_name)
    print("3. filter compiled and test commits done")
    # # 4. 提取出有测试用例的commit
    # merge_two_datasets(project_name)
    filter_commits_with_test_cases(project_name)
    # filter_commits_with_test_cases_with_commit_id(project_name, "3576d1ac2da7c7ee37f296599a99eaaf224e7b7c_79_86__125_133")
    print("4. filter commits with test cases done")
    # 5. 整理出最终的数据集
    generate_data_for_evaluation(project_name)
    print("5. generate data for evaluation done")

if __name__ == "__main__":
    project_name = "jgit"
    skip_commit_file = f'/Users/yisenxu/Downloads/Research/SOEN6491/Code/rag_refactoring/data/{project_name}/{project_name}_skip_commit_file.txt'
    pre_process_data(project_name, skip_commit_file)