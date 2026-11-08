# Agentic AI Learning Journey

A practical, project-based curriculum designed for backend engineers transitioning into Agentic AI.

## Learner Profile & Context
- **Background**: Backend Engineering (Java, Spring Boot).
- **Core Strengths**: Systems design, APIs, state management, reliability, testing, persistence.
- **Goal**: Master Agentic AI step-by-step from zero through hands-on code projects.
- **Language for Labs**: Python 3.14+ (for rapid prototyping, broad ecosystem support, and standard agent libraries).
- **Learning Philosophy**: "Learn by doing" — concepts introduced incrementally with runnable projects, zero hand-waving.
- **Folder Root**: `D:\Agentic AI`

---

## Curriculum Roadmap & Project Matrix

| Phase | Milestone Project | Key Concepts | Status |
| :--- | :--- | :--- | :--- |
| **0. Setup** | Virtual Environment & API Connectivity | Python venv, environment variables, API clients | Completed |
| **1. Foundations** | `01-llm-basics/` | Tokens, temperature, roles, structured JSON extraction | Completed |
| **2. Function Calling** | `02-tool-calling-engine/` | Schemas, tool definitions, execution dispatch loop, HITL | Completed |
| **3. The ReAct Agent** | `03-react-agent/` | Reason + Act loop, multi-step problem solving, scratchpad | Completed |
| **4. Memory & Context** | `04-memory-and-rag/` | Short-term vs long-term memory, embeddings, vector search | Completed |
| **5. Graph Workflows** | `05-stateful-workflows/` | State machines, cyclical graphs (LangGraph patterns) | Completed |
| **6. Multi-Agent Systems** | `06-multi-agent-collab/` | Supervisor-worker, debate, handoffs, human-in-the-loop | Completed |
| **7. MCP Architecture** | `07-mcp-agent-architecture/` | Model Context Protocol, FastMCP server, dynamic client | Completed |

---

## Part II: Production Engineering Track (started 2026-11-05)

**Assessment at start of Part II:** Concepts (phases 1–7) are covered. What's missing is the engineering discipline that makes agents trustworthy: no version control, no tests or evals, `print()` instead of tracing, security checks that can be bypassed, a toy RAG, nothing deployed.

**Learning format for every lesson:**
1. **Why**: the production failure this concept prevents.
2. **How**: the design, with backend (Java/Spring) analogies.
3. **Lab**: implement it in code.
4. **Exercise**: something you do yourself to prove you understand it.
5. **Log**: record the result in this README.

| Phase | Folder | Key Concepts | Status |
| :--- | :--- | :--- | :--- |
| **8. Engineering Foundations** | `08-engineering-foundations/` | Version control for prompts, pinned deps, shared LLM gateway, dependency injection, testing with fake LLMs | In Progress |
| **9. Evaluation (Evals)** | `09-evals/` | Non-determinism, golden datasets, trajectory vs outcome evals, pass@k, LLM-as-judge and calibrating it, regression in CI | Not Started |
| **10. Observability** | `10-observability/` | Structured logs, traces/spans (OpenTelemetry), token, cost and latency accounting, debugging agent runs | Not Started |
| **11. Reliability** | `11-reliability/` | Error taxonomy, timeouts, retries + idempotency, circuit breakers, context budgets, structured-output repair | Not Started |
| **12. Security & Guardrails** | `12-security/` | Prompt injection (direct and indirect), least-privilege tools, enforcement in code instead of in prompts, sandboxing, output filters | Not Started |
| **13. Production RAG** | `13-production-rag/` | Chunking, pgvector, hybrid search (BM25 + vectors), reranking, retrieval evals (recall@k, MRR) | Not Started |
| **14. Frameworks** | `14-frameworks/` | LangGraph vs your own engine, provider abstraction, when NOT to use a framework | Not Started |
| **15. Serving Agents** | `15-serving/` | FastAPI + async, job queues, durable HITL over an API, streaming, auth, rate limits, cost caps, Docker | Not Started |
| **16. Capstone** | `16-capstone/` | End-to-end production-grade agent service with evals, tracing and a deployment | Not Started |

---

## Log of Completed Lessons & Experiments

- **Setup & Workspace Initialization**:
  - Python runtime verified (`3.14.4`).
  - Workspace permissions granted on `D:\Agentic AI`.
  - Virtual environment `.venv` configured and connected to Gemini (`gemini-3.5-flash-lite`).
- **Phase 1: LLM Basics & Structured Outputs (`01-llm-basics/`)**:
  - `01_hello_llm.py`: Tested stateless generation, token tracking (`Prompt`, `Candidate`, `Total`), and system instructions enforcing role constraints.
  - `02_structured_output.py`: Used `Pydantic` models as strict DTOs (`response_schema`), parsing messy customer tickets directly into validated Java-like records with zero regex.
- **Phase 2: Tool Calling Engine (`02-tool-calling-engine/`)**:
  - `01_automatic_function_calling.py`: Converted standard Python functions into Gemini tools with automatic function calling (AFC), showing argument extraction, validation, and tool selection.
  - `02_manual_dispatch_loop.py`: Implemented manual dispatch loop disabling AFC, intercepting function calls, injecting a security guard / HITL authorization gate, and completing the 3-turn request/response handshake.
- **Phase 3: The ReAct Agent (`03-react-agent/`)**:
  - `01_react_loop.py`: Built an autonomous Reason-Act-Observe while-loop. Verified multi-step incident remediation across 5 chained tool calls (`search_incidents` -> `get_pod_metrics` -> `restart_pod` -> `send_ops_notification` -> final report) with error resilience, parallel calling support, and loop guardrails.
- **Phase 4: Memory & Context Management (`04-memory-and-rag/`)**:
  - `01_conversation_memory.py`: Contrasted `SlidingWindowMemory` (FIFO drop) with `SummaryBufferMemory` (rolling LLM-driven synthesis). Proved that summary buffers prevent catastrophic forgetting of early infrastructure parameters while keeping the active context window bounded.
- **Phase 5: Stateful Workflows & Graph Architectures (`05-stateful-workflows/`)**:
  - `01_state_machine_workflow.py`: Built an extensible, dependency-free StateGraph engine with deterministic transitions, conditional routers, and state reducers.
  - `02_cyclical_code_evaluator.py`: Implemented self-correcting cyclical feedback loops (LLM Generator $\rightarrow$ dynamic test execution $\rightarrow$ diagnostic feedback $\rightarrow$ re-generation until tests pass).
  - `03_persistent_checkpoint_hitl.py`: Engineered SQLite point-in-time state checkpointing, session isolation (`thread_id`), audit trails, and breakpoint gates (`interrupt_before`) for Human-In-The-Loop review, modification, and resumption.
- **Phase 6: Multi-Agent Systems & Collaboration (`06-multi-agent-collab/`)**:
  - `01_supervisor_orchestrator.py`: Implemented Hierarchical (Supervisor-Worker) pattern with an SRE Incident Commander cyclically dispatching DB, Network, and Infrastructure specialist agents.
  - `02_agent_handoffs_swarm.py`: Engineered Decentralized Peer-to-Peer Handoffs (The Swarm Pattern). Implemented tool-based transfer mechanics (`transfer_to_*`), dynamic active-agent pointer swapping, context ledger handovers, and full audit logging across Triage, Billing, and Fraud specialists.
  - `03_adversarial_code_review.py`: Engineered Adversarial Multi-Agent Debate (Maker-Checker Consensus). Orchestrated an autonomous feedback loop between a Senior Backend Developer Agent and a Red-Team Security Auditor Agent, culminating in sandbox test verification across balance updates, race conditions, negative amount attacks, and idempotency replays.
- **Phase 7: Model Context Protocol (MCP) (`07-mcp-agent-architecture/`)**:
  - `01_mcp_server.py`: Built an enterprise-grade MCP Server using official Python `mcp` SDK (`MCPServer`). Exposed all 3 MCP primitives over standard JSON-RPC 2.0: Tools (`query_database_readonly`, `transfer_funds_atomic`, `restart_service_container`), Resources (`banking://database/schema`, `system://telemetry/live`), and Prompts (`diagnose_payment_incident`). Added CLI inspection and self-test verification.
  - `02_mcp_client_agent.py`: MCP client bridge (stdio transport, handshake, MCP-to-Gemini schema translation), async ReAct loop over MCP, retry with backoff and a fallback model.

### Part II Log

- **2026-11-05: Production-readiness review of phases 1–7.** Gaps found: no git, no dependency manifest, zero tests/evals, scripted fallbacks hiding LLM failures (`06/03`), in-process `exec()` of LLM code, a `startswith("SELECT")` read-only check, no prompt-injection defense, unbounded context growth, `print()` logging. Part II roadmap created.
- **2026-11-05: Phase 8 / Lesson 8.1 started.** Reproducibility: version control and pinned dependencies (`08-engineering-foundations/README.md`).
