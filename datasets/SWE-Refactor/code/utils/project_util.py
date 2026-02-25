import os
import git


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

def get_previous_commit(repo_path, commit_hash):
    """
    Get the hash of the previous commit for a given commit hash.
    """
    try:
        # Initialize the repository object
        repo = git.Repo(repo_path)

        # Get the previous commit hash using git rev-parse
        previous_commit = repo.git.rev_parse(f"{commit_hash}^")
        print(f"Previous commit found: {previous_commit}")
        return previous_commit
    except git.exc.GitCommandError as e:
        raise Exception(f"Failed to retrieve previous commit: {e}")
    except Exception as e:
        raise Exception(f"An error occurred while finding the previous commit: {e}")


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


def get_project_structure(repo_path, commit_hash, file_path_before):
    """
    Main function to reset, checkout a commit, and return the project structure with .java files.
    """
    try:
        previous_commit = get_previous_commit(repo_path, commit_hash)

        # Reset and checkout the specified commit
        reset_and_checkout(repo_path, previous_commit)

        # Get project structure with .java files only
        structure_list = get_project_structure_with_java_files(repo_path, "", file_path_before)

        return structure_list
    except Exception as e:
        return f"Error: {e}"
