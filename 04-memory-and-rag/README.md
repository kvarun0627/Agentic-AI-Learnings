# Lab 04: Memory & Context Management (Short-Term & Long-Term)

This lab explores how production AI agents maintain state, control token budgets, and recall information across long conversations and external knowledge bases.

---

## 1. Why Naive Memory Fails

In earlier labs, agent memory was simply an unbounded Python list:
```python
contents.append(...)
```

In production systems, this creates three problems:
1. **Token Cost Explosion**: Sending 20+ turns on every single reasoning step multiplies input tokens quadratically.
2. **Context Window Limits**: When conversations or tool outputs exceed the context window, the model fails or drops input.
3. **Catastrophic Forgetting Across Sessions**: Raw Python lists disappear when the process terminates.

---

## 2. Lab 1: Short-Term Memory Strategies (`01_conversation_memory.py`)

We compared two architectural patterns for managing in-session conversation memory:

### Pattern A: Sliding Window Buffer (`SlidingWindowMemory`)
- **How it works**: Retains only the most recent $K$ turns (FIFO queue). Older messages are dropped.
- **Pros**: Zero extra LLM calls, deterministic token limit, zero latency overhead.
- **Cons**: Suffers from catastrophic forgetting. Early instructions, server IPs, and user constraints are permanently lost once pushed out of the window.

### Pattern B: Rolling Summary Buffer (`SummaryBufferMemory`)
- **How it works**: Keeps the most recent 1-2 turns in raw form for immediate conversational flow, but passes older turns to a background summarization prompt that maintains a compact, evolving narrative.
- **Pros**: Key facts (IP addresses, decisions, configuration flags) are retained indefinitely with a fixed token footprint.
- **Cons**: Requires an extra lightweight background LLM call to update the summary when thresholds are exceeded.

### Verified Test Run:
```
Testing Recall: "What is the server IP and port for the payment gateway?"

>>> Sliding Window Agent:
Response: "I do not have access to internal infrastructure details..." (FAILED - Pushed out of buffer)

>>> Summary Buffer Agent:
Response: "Based on our earlier configuration, the payment gateway server IP address is 10.0.4.55 and the port is 8443." (SUCCESS - Retained in summary)
```

---

## 3. Lab 2: Long-Term Memory & Vector Embeddings (`02_vector_embeddings_rag.py`)

In this lab, we build an **in-memory vector database** from scratch and implement semantic retrieval (RAG foundation).

### Key Concepts:
1. **Dense Vector Embeddings (`gemini-embedding-001`)**: Converts arbitrary text chunks into high-dimensional points (3,072 dimensions) that capture semantic meaning.
2. **Cosine Similarity**: Measures the cosine of the angle between two embedding vectors:
   $$\text{similarity}(A, B) = \frac{A \cdot B}{\|A\| \|B\|}$$
3. **Semantic Search over Exact Keywords**: Queries retrieve relevant documents even when zero identical keywords are shared.

### Verified Test Run:
```
Query: "A container keeps dying unexpectedly with termination code 137"
Matches:
  [1] Score: 0.7597 | ID: RB-003 | Title: Kubernetes CrashLoopBackOff (OOMKilled)
  [2] Score: 0.6129 | ID: RB-002 | Title: Redis Memory Exhaustion (OOM)
```

---

## 4. Lab 3: Autonomous RAG-Enabled Agent (`03_rag_enabled_agent.py`)

Equipping an autonomous ReAct SRE agent with a dynamic vector-search tool (`search_runbooks`) to resolve production outages without hallucination.

### Execution Trajectory:
1. **Alert Ingestion**: `P1 Incident on payment-service. Checkout API is timing out and throwing 503 errors.`
2. **Cycle 1 (Investigate)**: Calls `get_service_logs("payment-service")` -> reveals `HikariPool-1 - Connection is not available`.
3. **Cycle 2 (RAG Retrieval)**: Calls `search_runbooks("HikariPool Connection is not available...")` -> retrieves **RB-001** (*PostgreSQL Connection Pool Starvation*).
4. **Cycle 3 (Remediate)**: Executes `apply_remediation("payment-service", action="scale_db_pool", param="50")` strictly following runbook instructions.
5. **Cycle 4 (Post-Mortem)**: Verifies service is healthy and generates a root-cause summary.
