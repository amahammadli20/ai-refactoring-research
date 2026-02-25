import json
import pickle

from rag.rag_embedding import remove_java_comments


class Refactoring:
    def __init__(self, refactoring_data):
        """initialize Refactoring object."""
        self.type = refactoring_data.get("type")
        self.source_code_before = refactoring_data.get("sourceCodeBeforeRefactoring")
        self.file_path_before = refactoring_data.get("filePathBefore")
        self.is_pure_refactoring = refactoring_data.get("isPureRefactoring", False)
        self.commit_id = refactoring_data.get("commitId")
        self.package_name_before = refactoring_data.get("packageNameBefore")
        self.class_name_before = refactoring_data.get("classNameBefore")
        self.method_name_before = refactoring_data.get("methodNameBefore")
        self.invoked_method = refactoring_data.get("invokedMethod", "")
        self.class_signature_before = refactoring_data.get("classSignatureBefore")
        self.source_code_after = refactoring_data.get("sourceCodeAfterRefactoring")
        self.diff_source_code = refactoring_data.get("diffSourceCode")
        self.unique_id = refactoring_data.get("uniqueId")
        self.context_description = refactoring_data.get("contextDescription")
        self.description = refactoring_data.get("description")

    def to_dict(self):
        """Convert Refactoring object to dictionary for serialization storage."""
        return {
            "type": self.type,
            "sourceCodeBeforeRefactoring": self.source_code_before,
            "filePathBefore": self.file_path_before,
            "isPureRefactoring": self.is_pure_refactoring,
            "commitId": self.commit_id,
            "packageNameBefore": self.package_name_before,
            "classNameBefore": self.class_name_before,
            "methodNameBefore": self.method_name_before,
            "invokedMethod": self.invoked_method,
            "classSignatureBefore": self.class_signature_before,
            "sourceCodeAfterRefactoring": self.source_code_after,
            "diffSourceCode": self.diff_source_code,
            "uniqueId": self.unique_id,
            "contextDescription": self.context_description,
            "description": self.description
        }


class RefactoringRepository:
    def __init__(self, data):
        self.refactoring_map = self._build_map(data)

    def _build_map(self, data):
        """build a dictionary with contextDescription as the key."""
        refactoring_map = {}
        for commit in data.get("commits", []):
            for refactoring_data in commit.get("refactoringAnalyses", []):
                if 'contextDescription' in refactoring_data:
                    refactoring = Refactoring(refactoring_data)
                    refactoring_map[refactoring.context_description + '\n' + remove_java_comments(refactoring.source_code_before)] = refactoring.to_dict()
        return refactoring_map

    def save_to_file(self, filename, format="json"):
        """convert refactoring_map to JSON or Pickle file."""
        with open(filename, "w" if format == "json" else "wb") as f:
            if format == "json":
                json.dump(self.refactoring_map, f, indent=4)
            elif format == "pickle":
                pickle.dump(self.refactoring_map, f)

    @staticmethod
    def load_from_file(filename, format="json"):
        """从 JSON 或 Pickle 文件加载 refactoring_map。"""
        with open(filename, "r" if format == "json" else "rb") as f:
            return json.load(f) if format == "json" else pickle.load(f)

    def find_by_context_description(self, description):
        """search refactoring by contextDescription."""
        return self.refactoring_map.get(description, "Refactoring not found")
