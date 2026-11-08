import os
import math
from typing import List, Dict, Any
from dotenv import load_dotenv
from google import genai

# =====================================================================
# Setup & Initialization
# =====================================================================
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

client = genai.Client(api_key=api_key)
EMBEDDING_MODEL = "gemini-embedding-001"


# =====================================================================
# Math Helper: Cosine Similarity
# =====================================================================
def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculates the cosine similarity between two vector lists.
    
    Formula: (A · B) / (||A|| * ||B||)
    Returns a score between -1.0 and 1.0 (1.0 = identical direction/meaning).
    """
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))
    
    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0
        
    return dot_product / (magnitude_a * magnitude_b)


# =====================================================================
# Core Architecture: In-Memory Vector Store
# =====================================================================
class InMemoryVectorStore:
    """A lightweight vector database built from scratch.
    
    Stores documents alongside their dense vector embeddings and
    performs semantic similarity search using cosine distance.
    """
    def __init__(self, client: genai.Client, model: str):
        self.client = client
        self.model = model
        self.documents: List[Dict[str, Any]] = []

    def _generate_embedding(self, text: str) -> List[float]:
        """Calls Gemini API to convert text into a dense vector (list of numbers)."""
        response = self.client.models.embed_content(
            model=self.model,
            contents=text
        )
        return response.embeddings[0].values

    def add_document(self, doc_id: str, title: str, content: str):
        """Generates embedding for content and stores the record."""
        print(f"  [VectorStore] Indexing document: '{title}'...")
        embedding = self._generate_embedding(content)
        
        self.documents.append({
            "id": doc_id,
            "title": title,
            "content": content,
            "embedding": embedding
        })

    def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Finds the top K most semantically relevant documents for a query."""
        print(f"\n[VectorStore] Embedding user query: \"{query}\"")
        query_vector = self._generate_embedding(query)

        scored_docs = []
        for doc in self.documents:
            score = cosine_similarity(query_vector, doc["embedding"])
            scored_docs.append({
                "id": doc["id"],
                "title": doc["title"],
                "content": doc["content"],
                "score": score
            })

        # Sort documents by similarity score in descending order (highest score first)
        scored_docs.sort(key=lambda d: d["score"], reverse=True)
        return scored_docs[:top_k]


# =====================================================================
# Demonstration & Semantic Search Verification
# =====================================================================
def run_lab():
    print("=" * 75)
    print(" LAB: Dense Vector Embeddings & Vector Search (RAG)")
    print("=" * 75)

    store = InMemoryVectorStore(client=client, model=EMBEDDING_MODEL)

    # 1. Knowledge Base: Production Engineering Runbooks
    runbooks = [
        {
            "id": "RB-001",
            "title": "PostgreSQL Connection Pool Starvation",
            "content": "Symptoms: HikariCP connection timeouts, HTTP 503 errors. "
                       "Root Cause: Leaked connections or slow queries holding db pool sessions. "
                       "Fix: Increase maxPoolSize in application.yml, review pg_stat_activity, and configure leakDetectionThreshold."
        },
        {
            "id": "RB-002",
            "title": "Redis Memory Exhaustion (OOM)",
            "content": "Symptoms: Command 'OOM command not allowed when used memory > maxmemory'. "
                       "Root Cause: Cache keys written without TTL, evicting cache items failed under volatile-lru policy. "
                       "Fix: Set TTL on key writes, change eviction policy to allkeys-lru, scale up Redis node memory."
        },
        {
            "id": "RB-003",
            "title": "Kubernetes CrashLoopBackOff (OOMKilled)",
            "content": "Symptoms: Pod restarts continuously with exit code 137. "
                       "Root Cause: JVM max heap exceeds container cgroup memory limits. "
                       "Fix: Configure -XX:MaxRAMPercentage=75.0 and raise pod memory limits in deployment spec."
        },
        {
            "id": "RB-004",
            "title": "Kafka Consumer Group Rebalance Storm",
            "content": "Symptoms: Frequent consumer rebalances, processing lag spikes. "
                       "Root Cause: max.poll.interval.ms exceeded due to slow record processing in batch listener. "
                       "Fix: Decrease max.poll.records, optimize downstream processing, or increase max.poll.interval.ms."
        }
    ]

    print("\n--- Step 1: Ingesting & Embedding Runbooks into Vector Store ---")
    for rb in runbooks:
        store.add_document(doc_id=rb["id"], title=rb["title"], content=rb["content"])

    sample_dim = len(store.documents[0]["embedding"])
    print(f"\nIndexed {len(store.documents)} runbooks successfully.")
    print(f"Embedding vector dimension per document: {sample_dim} floating-point numbers.")

    # 2. Test Semantic Search with Non-Matching Keywords
    test_queries = [
        "My Java Spring microservice is failing to get connections from the database pool and timing out",
        "A container keeps dying unexpectedly with termination code 137"
    ]

    print("\n" + "=" * 75)
    print("--- Step 2: Semantic Matching (No Exact Keyword Matches Needed) ---")
    print("=" * 75)

    for query in test_queries:
        results = store.search(query=query, top_k=2)
        print(f"\nTop matches for query: \"{query}\"")
        for rank, res in enumerate(results, 1):
            print(f"  [{rank}] Score: {res['score']:.4f} | ID: {res['id']} | Title: {res['title']}")
            print(f"      Snippet: {res['content'][:110]}...")

    print("\n" + "=" * 75)
    print(" KEY TAKEAWAY:")
    print(" Notice that query 2 did not mention 'Kubernetes' or 'OOMKilled' or 'CrashLoopBackOff',")
    print(" yet it ranked RB-003 at the top because 'container keeps dying with code 137'")
    print(" is geometrically closest in meaning to 'Pod restarts with exit code 137'.")
    print("=" * 75)


if __name__ == "__main__":
    run_lab()
