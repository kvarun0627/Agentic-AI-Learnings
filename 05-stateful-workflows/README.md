# Phase 05: Stateful Workflows & Graph Architectures

Welcome to Phase 5. In earlier phases, we explored:
1. **Tool Calling (`02-tool-calling-engine/`)**: Giving LLMs access to APIs.
2. **The ReAct Loop (`03-react-agent/`)**: An autonomous while-loop where the LLM decides its own tools.
3. **Memory & RAG (`04-memory-and-rag/`)**: Managing context windows, vector search, and runbooks.

---

## 1. Why Graphs? (Moving Beyond the Free-Form ReAct Loop)

In production enterprise systems (especially from a Backend/Spring Boot background), an unconstrained `while step <= max_steps` ReAct agent has serious weaknesses:

1. **Unpredictable Execution Paths**: An open-ended ReAct agent might wander, call tools out of order, or hallucinate arbitrary sequences.
2. **Lack of Deterministic Governance**: Critical workflows (payment processing, database migrations, security scans) require strict stage gates: *Step B must only execute if Step A passes validation*.
3. **Complex Branching & Cycles**: ReAct loops don't handle structured conditional branching (e.g. routing to specialized sub-flows) or formal self-correction loops cleanly.

### The Graph Paradigm (LangGraph Pattern):
- **State**: A centralized, immutable-update blackboard (`TypedDict` or `Pydantic`) passed between nodes.
- **Nodes**: Python functions representing discrete tasks (LLM prompts, rule-based validations, API calls). Each node receives the current state and returns a dictionary of state updates.
- **Edges**: Deterministic connections specifying which node runs next (`A -> B`).
- **Conditional Edges (Routers)**: Functions that inspect current state and decide the next node dynamically (`if state["category"] == "security" -> Node C`).

```
                ┌─────────┐
                │  START  │
                └────┬────┘
                     │
                     ▼
             ┌───────────────┐
             │ Triage & Plan │
             └───────┬───────┘
                     │  (Conditional Router)
         ┌───────────┼───────────┐
         ▼           ▼           ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ Security │ │ Database │ │ Network  │
   └─────┬────┘ └────┬─────┘ └────┬─────┘
         └───────────┼────────────┘
                     │
                     ▼
             ┌───────────────┐
             │  Resolution   │
             └───────┬───────┘
                     │
                     ▼
                ┌─────────┐
                │   END   │
                └─────────┘
```

---

## 2. Phase 5 Project Roadmap

| Lab | Script | Key Concepts | Status |
| :--- | :--- | :--- | :--- |
| **Lab 01** | `01_state_machine_workflow.py` | Building a pure-Python StateGraph engine from scratch, deterministic nodes, conditional routing, state reducers. | Completed |
| **Lab 02** | `02_cyclical_code_evaluator.py` | Cyclical self-correction graphs (Generator -> Validator -> Conditional Loop back with error feedback until passing or max retries). | Completed |
| **Lab 03** | `03_persistent_checkpoint_hitl.py` | State persistence (checkpointing to disk/DB), pause-and-resume workflows, and Human-In-The-Loop approval gates. | Completed |

---

## 3. Lab Highlights

- **Lab 01 (`01_state_machine_workflow.py`)**: Explores core state graphs, routing triage, and deterministic state reducers.
- **Lab 02 (`02_cyclical_code_evaluator.py`)**: Demonstrates cyclical feedback loops where an LLM repeatedly writes code, executes unit tests dynamically, and auto-corrects based on test failure tracebacks.
- **Lab 03 (`03_persistent_checkpoint_hitl.py`)**: Introduces SQLite persistence, thread IDs, `interrupt_before` breakpoints for Human-In-The-Loop approval, state inspection/patching, and workflow resumption.
