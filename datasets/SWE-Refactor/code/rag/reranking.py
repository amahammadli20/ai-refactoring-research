import os
from typing import List, Optional, Any

from rerankers import Reranker


class Reranking:
    def __init__(self, model_name, model_type: Optional[str] = None,
                 api_key: Optional[str] = None):
        """
        Initializes the Reranking model.

        Parameters:
            model_type (str): The type of the model to use for reranking (default is 'cross-encoder').
            model_name (Optional[str]): Specific model name if using a specific cross-encoder or GPT variant.
            api_key (Optional[str]): API key for models requiring authentication (e.g., GPT).
        """
        # Specify model type for cross-encoder or any other model type to avoid warnings
        if model_type and api_key:
            self.ranker = Reranker(model_name, model_type=model_type, api_key=api_key)
        elif api_key:
            self.ranker = Reranker(model_name, api_key=api_key)
        else:
            self.ranker = Reranker(model_name)

    def rerank(self, query: str, documents: List[str], doc_ids: Optional[List[int]] = None,
               metadata: Optional[List[dict]] = None) -> Any:
        """
        Reranks the given documents based on the query.

        Parameters:
            query (str): The query string for reranking.
            documents (List[str]): List of documents to rerank.
            doc_ids (Optional[List[int]]): List of document IDs (optional).
            metadata (Optional[List[dict]]): Metadata for each document (optional).

        Returns:
            Any: Ranked results containing the reranked documents.
        """
        # If doc_ids are not provided, generate them
        if doc_ids is None:
            doc_ids = list(range(len(documents)))

        # Rank the documents based on the query
        results = self.ranker.rank(query, documents, doc_ids=doc_ids, metadata=metadata)
        return results


# Example Usage
if __name__ == "__main__":
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    # Initialize the Reranking class using a GPT model
    reranker = Reranking("cross-encoder")

    # Define the query and documents
    query = "I love you"
    documents = [
        "I hate you", "I really like you"
    ]

    # Rerank the documents based on the query
    ranked_results = reranker.rerank(query, documents)

    # Display the results
    for result in ranked_results.results:
        print(f"Rank: {result.rank}, Score: {result.score}, Document: {result.document.text}")
