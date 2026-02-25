import csv
import json
from collections import defaultdict


def load_json(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def save_json(file_path, output_data):
    with open(file_path, 'w') as f:
        json.dump(output_data, f, indent=4)

project_name ="gson"
input_path = 'data/refactoring_info/' + project_name + '_refactoring_info.json'
output_path = 'data/output/' + project_name +'_em_refactoring.json'
output_path_commits = ''



def extract_method_refactorings(input_data):
    commits = input_data['commits']
    filtered_commits = [
        commit for commit in commits
        if any(refactoring['type'] == "Extract Method" for refactoring in commit['refactorings'])
    ]

    save_json(output_path, {"commits": filtered_commits})

def extract_pure_refactoring_data(json_file, output_file):
    # 读取 JSON 文件
    with open(json_file, 'r') as file:
        data = json.load(file)

    # 使用集合存储唯一的 (url, commitId) 对
    unique_entries = set()

    # 遍历 JSON 数据，查找包含 pureRefactoring 为 true 的条目
    for commit in data.get('commits', []):
        # 检查每个 refactoring
        for refactoring in commit.get('refactorings', []):
            if refactoring.get('isPureRefactoring') is True:
                url = commit.get('url')
                commit_id = refactoring.get('commitId')
                # 将 (url, commitId) 添加到集合中
                unique_entries.add((url, commit_id))

    # 将结果写入文件
    # with open(output_file, mode='w', newline='') as file:
    #     writer = csv.writer(file)
    #     writer.writerow(["URL", "Commit ID", "Compile Result"])
    #
    #     for url, commit_id in unique_entries:
    #         writer.writerow([url, commit_id, ""])
    with open(output_file, 'w') as output:
        for url, commit_id in unique_entries:
            output.write(f"{url},{commit_id}\n")


def count_refactoring_types(input_data):
    commits = input_data['commits']
    # 创建字典来统计 refactoring 类型的数量
    refactoring_count = defaultdict(int)

    # 遍历所有的 commits 并统计 refactoring 的 type
    for commit in commits:
        for refactoring in commit['refactorings']:
            refactoring_type = refactoring['type']
            refactoring_count[refactoring_type] += 1

    # 按照数量进行倒序排序
    sorted_refactoring_count = sorted(refactoring_count.items(), key=lambda x: x[1], reverse=True)

    # 打印每种 refactoring 类型的数量（按数量倒序）
    for refactoring_type, count in sorted_refactoring_count:
        print(f"{refactoring_type}: {count}")

if __name__ == "__main__":
    json_file_path = 'data/refactoring_info/refactoring_miner_em_refactoring_w_sc_v2.json'  # 修改为你的 JSON 文件路径
    output_file_path = 'data/output/pure_refactorings_projects_compile.txt'  # 修改为你想要保存结果的文件路径
    extract_pure_refactoring_data(json_file_path, output_file_path)
    print(f"Results have been written to {output_file_path}")

