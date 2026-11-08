# Phase 07: Model Context Protocol (MCP) & Extensible Agent Architecture

Welcome to Phase 7. In this phase, you transition from hardcoding tools directly into agent runtimes to the industry-standard **Model Context Protocol (MCP)**.

---

## 1. What is MCP? (The Backend Engineering Analogy)

In traditional enterprise software, integrations without standards lead to the **$N \times M$ complexity crisis**:
- If you have 5 IDEs and 10 programming languages, without a standard you need $5 \times 10 = 50$ custom plugins.
- Microsoft solved this with **LSP (Language Server Protocol)**: Every language builds **1 Language Server**, and every IDE builds **1 LSP Client**. The complexity drops to $N + M$.
- Similarly, in databases, **JDBC/ODBC** standardized SQL drivers so applications don't write custom socket code for Oracle, Postgres, and MySQL.

In the AI ecosystem:
- Before MCP, every agent framework (LangChain, AutoGen, CrewAI, Gemini SDK, Claude Desktop, Cursor) had its own proprietary way to declare and invoke tools.
- **MCP (Model Context Protocol)** standardizes this via **JSON-RPC 2.0**.
- A tool or database developer writes **one MCP Server**. Any **MCP Client** (your agent, an IDE, a desktop assistant) can connect to it and instantly discover and invoke its capabilities.

```
                      THE MCP ARCHITECTURE
  
   ┌──────────────────────────────────────────────┐
   │            MCP Host / Client                 │
   │  (Autonomous Gemini Agent / CLI / IDE)       │
   └───────────────┬──────────────────────────────┘
                   │
                   │ Standard JSON-RPC 2.0
                   │ (Transport: stdio or SSE/HTTP)
                   ▼
   ┌──────────────────────────────────────────────┐
   │                MCP Server                    │
   │      (Independent Subprocess / Service)      │
   │                                              │
   │  1. Tools     : Callable Functions (Mutate)  │
   │  2. Resources : Read-Only Data (Query)       │
   │  3. Prompts   : Standardized Templates       │
   └──────────────────────────────────────────────┘
```

---

## 2. The 3 Core Primitives of MCP

1. **Tools (Model-Controlled)**:
   - Executable actions with strict JSON Schema arguments (e.g. `execute_sql`, `restart_service`, `create_github_issue`).
   - The LLM decides when to invoke them to take action or fetch computed data.
2. **Resources (Application-Controlled)**:
   - Analogous to GET endpoints or static files (e.g. `system://metrics/live`, `db://schema/accounts`).
   - Read-only data attached to context to ground the model without executing functions.
3. **Prompts (User-Controlled)**:
   - Pre-packaged prompt engineering templates (e.g. `analyze-incident-logs(service_name, severity)`).
   - Allows servers to suggest standard workflows to clients.

---

## 3. Protocol Wire Lifecycle (JSON-RPC 2.0 over stdio)

```
Client (Agent)                                      Server (FastMCP)
   │                                                      │
   ├────── initialize (protocolVersion, capabilities) ───►│
   │◄───── response (serverInfo, capabilities) ───────────┤
   ├────── notifications/initialized ────────────────────►│
   │                                                      │
   ├────── tools/list ───────────────────────────────────►│
   │◄───── response (List of Tool Schemas) ───────────────┤
   │                                                      │
   │  [Agent reasons using Gemini LLM & invokes tool]     │
   │                                                      │
   ├────── tools/call (name="query_db", arguments={...}) ─►│
   │◄───── response (content=[{type: "text", text: ...}])─┤
```

---

## 4. Phase 7 Lab Roadmap

| Lab | Script | Pattern | Focus | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Lab 01** | `01_mcp_server.py` | **MCP Server (MCPServer)** | Exposes enterprise backend microservices (SQLite database queries, transaction management, system resource metrics) over standard MCP JSON-RPC protocol. | Completed |
| **Lab 02** | `02_mcp_client_agent.py` | **Autonomous MCP Agent** | Subprocess transport manager that connects to the MCP Server, queries `tools/list`, maps MCP schemas directly into Gemini Function Declarations, and runs an autonomous ReAct loop over MCP. | Completed |

---

## 5. How to Run Lab 02: Autonomous MCP Client Agent

### Quick Run (All Scenarios)
```bash
python 07-mcp-agent-architecture/02_mcp_client_agent.py
```

### Run Specific Demonstration Scenarios
- **Scenario 1 (SQL Investigation & Read-Only Audit):**
  ```bash
  python 07-mcp-agent-architecture/02_mcp_client_agent.py --scenario 1
  ```
- **Scenario 2 (Multi-Step ACID Transfer & Verification):**
  ```bash
  python 07-mcp-agent-architecture/02_mcp_client_agent.py --scenario 2
  ```
- **Scenario 3 (Incident Triage with MCP Prompt Templates & Resources):**
  ```bash
  python 07-mcp-agent-architecture/02_mcp_client_agent.py --scenario 3
  ```

### Run Custom Prompt
```bash
python 07-mcp-agent-architecture/02_mcp_client_agent.py --prompt "Query the accounts table and tell me which customer has the lowest balance."
```

### Interactive REPL Shell
```bash
python 07-mcp-agent-architecture/02_mcp_client_agent.py --interactive
```
