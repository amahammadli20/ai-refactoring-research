import json
import os
import re
from collections import defaultdict

import yaml
from tqdm import tqdm

import chromadb

from bm25 import BM25


current_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(current_dir, '..', 'config.yaml')
config_path = os.path.abspath(config_path)
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)
# OpenAI API key
chromadb_host = config['chromadb_host']

chroma_client = chromadb.HttpClient(host=chromadb_host, port=8000)
from chromadb.utils import embedding_functions


def remove_java_comments(java_code):
    # regex pattern to match comments
    pattern = r"(//.*?$|/\*.*?\*/|/\*\*.*?\*/)"
    # remove comments
    cleaned_code = re.sub(pattern, "", java_code, flags=re.DOTALL | re.MULTILINE)
    return cleaned_code


# Create a new collection
default_ef = embedding_functions.DefaultEmbeddingFunction();
# chroma_client.delete_collection(name="refactoring_collection")



def add_documents_to_chroma(collection_name, file_path, num_count):
    collection = chroma_client.get_or_create_collection(name=collection_name)
    # create a new collection
    with open(file_path, 'r') as file:
        data = json.load(file)
    documents = []
    metadata_refactoring = []
    ids = []
    group_documents = defaultdict(list)
    unique_ids_set = set()
    count = 0
    # read the data and add to the collection
    for commit in tqdm(data['commits']):
        if "refactoringAnalyses" not in commit:
            continue
        if count >= num_count:
            break
        for refactoring in commit['refactoringAnalyses']:
            unique_id = refactoring['uniqueId']

            # check if the uniqueId is already in the set
            if unique_id not in unique_ids_set and refactoring['isPureRefactoring']:
                # get the source code before refactoring
                source_before = remove_java_comments(refactoring['sourceCodeBeforeRefactoring'])
                context_description = refactoring['contextDescription']
                refactoring_data_to_store = {
                    "type": refactoring['type'],
                    "sourceCodeBeforeRefactoring": refactoring['sourceCodeBeforeRefactoring'],
                    "filePathBefore": refactoring['filePathBefore'],
                    "isPureRefactoring": refactoring['isPureRefactoring'],
                    "commitId": refactoring['commitId'],
                    "packageNameBefore": refactoring['packageNameBefore'],
                    "classNameBefore": refactoring['classNameBefore'],
                    "methodNameBefore": refactoring['methodNameBefore'],
                    "invokedMethod": "invokedMethod" in refactoring and refactoring['invokedMethod'] or "",
                    "classSignatureBefore": "classSignatureBefore" in refactoring and refactoring['classSignatureBefore'] or "",
                    "sourceCodeAfterRefactoring": refactoring['sourceCodeAfterRefactoring'],
                    "diffSourceCode": refactoring['diffSourceCode'],
                    "uniqueId": refactoring['uniqueId'],
                    "contextDescription": refactoring['contextDescription'],
                }
                # add the document to the list
                documents.append(context_description + '\n' + source_before)
                group_documents[refactoring['type']].append(context_description + '\n' + source_before)
                metadata_refactoring.append(refactoring_data_to_store)
                ids.append(unique_id)
                count += 1

                # add the uniqueId to the set
                unique_ids_set.add(unique_id)
            else:
                if unique_id in unique_ids_set:
                    print(f"Skipping duplicate uniqueId: {unique_id}")


    # add the documents to the collection
    if documents:
        collection.add(
            documents=documents,
            metadatas=metadata_refactoring,
            ids=ids,
        )
        # add document to bm25
        for key, value in group_documents.items():
            bm25_model = BM25(value)
            bm25_model.save_model(f'data/model/{collection_name}_{key}_bm25result.pkl')
    else:
        print("No new unique IDs to add.")

def search_chroma(text,n_results,collection_name, refactoring_type):

    collection = chroma_client.get_or_create_collection(name=collection_name)
    # test the search
    results = collection.query(
        query_texts = [text],  # search query
        n_results = n_results,  # return top n results
        where = {
            "type": refactoring_type
        }
    )
    return results




