class ReciprocalRankFusion:
    def __init__(self, k=60):
        """
        Initialize the RRF instance with a configurable constant k.
        Args:
            k (int): A small positive constant to prevent division by zero (default is 60).
        """
        self.k = k

    def fuse(self, ranked_lists):
        """
        Compute the Reciprocal Rank Fusion (RRF) score for each document.

        Args:
            ranked_lists (list of lists): Each inner list is a ranked list of document IDs.

        Returns:
            dict: A dictionary with document IDs as keys and their RRF scores as values.
        """
        rrf_scores = {}

        for ranked_list in ranked_lists:
            for rank, doc_id in enumerate(ranked_list):
                # Compute the reciprocal rank for the document
                score = 1 / (self.k + rank + 1)

                # Accumulate the score for the document
                if doc_id in rrf_scores:
                    rrf_scores[doc_id] += score
                else:
                    rrf_scores[doc_id] = score

        return rrf_scores

    def get_top_n(self, rrf_scores, n=10):
        """
        Get the top N documents based on RRF scores.

        Args:
            rrf_scores (dict): A dictionary with document IDs as keys and their RRF scores as values.
            n (int): The number of top documents to return (default is 10).

        Returns:
            list: A list of tuples (doc_id, score) sorted by score in descending order.
        """
        return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:n]


# Example usage
if __name__ == "__main__":
    # Example ranked lists from different models/sources
    ranked_lists = [
        ['doc1', 'doc2', 'doc3', 'doc4'],
        ['doc2', 'doc4', 'doc3', 'doc5'],
        ['doc2', 'doc1', 'doc3', 'doc6']
    ]

    # Initialize the RRF fusion object
    rrf = ReciprocalRankFusion(k=60)

    # Compute RRF scores
    scores = rrf.fuse(ranked_lists)
    print("RRF Scores:", scores)

    # Get the top 3 documents
    top_docs = rrf.get_top_n(scores, n=3)
    print("Top 3 Documents:", top_docs)
