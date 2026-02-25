import os
import subprocess

import git


def run_command(command):
    """运行系统命令并捕获输出"""
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    success = result.returncode == 0
    if success:
        print(f"Command succeeded: {command}")
    else:
        print(f"Command failed: {command}\n{result.stderr}")
    return success, result

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

def get_previous_commit(commit_id):
    """获取指定 commit 的上一个 commit"""
    result = subprocess.run(f"git rev-parse {commit_id}~1", shell=True, text=True, capture_output=True)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        print(f"Failed to get the previous commit for {commit_id}: {result.stderr}")
        return None

def reset_and_checkout(repo_path, commit_hash):
    """
    Reset the repository and checkout a specific commit.
    """
    repo = git.Repo(repo_path)
    try:
        # Reset to ensure a clean working tree
        repo.git.reset('--hard')
        print("Repository reset to clean state.")

        # Checkout the specified commit
        repo.git.checkout(commit_hash)
        print(f"Checked out commit: {commit_hash}")
    except Exception as e:
        raise Exception(f"Error during reset or checkout: {e}")


def get_project_structure_with_java_files(root_dir, relative_to="", file_path_before=""):
    """
    Recursively build the project structure, only including .java files, with relative paths.
    Returns a list of .java file paths.
    """
    if not relative_to:
        relative_to = root_dir  # Set the base path for relative paths
    file_name_list = file_path_before.split("/")
    parent_file_name = file_name_list[0] + "/" + file_name_list[1] + "/" + file_name_list[2]
    java_files = []

    for item in sorted(os.listdir(root_dir)):
        path = os.path.join(root_dir, item)
        relative_path = os.path.relpath(path, relative_to)
        # Filter out build and target directories
        if os.path.isdir(path):
            # Recurse into directories
            java_files.extend(get_project_structure_with_java_files(path, relative_to, file_path_before))
        elif item.endswith(".java"):
            # Add .java files
            if parent_file_name in relative_path:
                java_files.append(relative_path)

    return java_files

def read_java_file_content_in_commit(repo_path, commit_hash, file_path):
    try:
        # Get the hash of the previous commit
        previous_commit = get_previous_commit(repo_path, commit_hash)

        # Reset and checkout the specified commit
        reset_and_checkout(repo_path, previous_commit)

        # Get project structure with .java files only
        structure = read_java_file_content(file_path)
        return structure
    except Exception as e:
        return f"Error: {e}"

def read_java_file_content(file_path):
    """
    Read the content of a file given its full path.
    """
    if not os.path.exists(file_path):
        return f"Error: {file_path} does not exist."

    if not os.path.isfile(file_path):
        return f"Error: {file_path} is not a valid file."
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


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

def get_project_structure(repo_path, commit_hash, file_path_before):
    """
    Main function to reset, checkout a commit, and return the project structure with .java files.
    """
    try:
        checkout_previous_commit(commit_hash, repo_path)
        # Get project structure with .java files only
        structure_list = get_project_structure_with_java_files(repo_path, "", file_path_before)

        return structure_list
    except Exception as e:
        return f"Error: {e}"


# Example usage
if __name__ == "__main__":
    # Replace with your repo path and commit hash
    repo_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/gson"
    commit_hash = "46ab704221608fb6318d110f1b0c2abca73a9ea2"

    # Get project structure
    project_structure = get_project_structure(repo_path, commit_hash)

    # Example: Read the content of a specific file
    file_path = "/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/gson/gson/src/test/java/com/google/gson/ExposeAnnotationExclusionStrategyTest.java"
    file_content = read_java_file_content(file_path)
    file_content = read_java_file_content_in_commit(repo_path, commit_hash, file_path)
    # Output results
    print("Filtered Project Structure (Java files only):")
    print(project_structure)
    print("\nFile Content:")
    print(file_content)
