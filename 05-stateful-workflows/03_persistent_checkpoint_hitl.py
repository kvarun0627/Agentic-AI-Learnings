import os
import json
import sqlite3
import datetime
from typing import Dict, Any, Callable, List, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

# =====================================================================
# 1. Setup & Gemini Client
# =====================================================================
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.5-flash-lite"
END = "__END__"


# =====================================================================
# 2. SQLite Persistent Checkpointer (The Foundation of Durability)
# =====================================================================
class SqliteCheckpointer:
    """Persists workflow states into a local SQLite database.
    
    This mirrors LangGraph's SqliteSaver, enabling:
    1. Long-running asynchronous execution (workflows surviving process restarts).
    2. Human-In-The-Loop approval gates (pause and resume after hours/days).
    3. Time-travel auditing and post-mortem incident debugging.
    """
    def __init__(self, db_path: str = "workflow_checkpoints.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    step_count INTEGER NOT NULL,
                    node_name TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_thread ON checkpoints(thread_id)")
            conn.commit()

    def put(self, thread_id: str, step_count: int, node_name: str, state: Dict[str, Any]):
        """Saves a point-in-time snapshot of the workflow state."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (thread_id, step_count, node_name, state_json)
                VALUES (?, ?, ?, ?)
                """,
                (thread_id, step_count, node_name, json.dumps(state))
            )
            conn.commit()

    def get_latest(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent state checkpoint for a thread."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT thread_id, step_count, node_name, state_json, created_at
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY checkpoint_id DESC
                LIMIT 1
                """,
                (thread_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "thread_id": row["thread_id"],
                "step_count": row["step_count"],
                "node_name": row["node_name"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"]
            }

    def list_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """Returns the full chronological history/timeline for auditing."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT checkpoint_id, step_count, node_name, created_at
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY checkpoint_id ASC
                """,
                (thread_id,)
            )
            return [dict(row) for row in cursor.fetchall()]


# =====================================================================
# 3. StateGraph Engine with Checkpointing & Interrupts (HITL)
# =====================================================================
class StateGraph:
    def __init__(self):
        self.nodes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.edges: Dict[str, str] = {}
        self.conditional_edges: Dict[str, tuple[Callable[[Dict[str, Any]], str], Dict[str, str]]] = {}
        self.entry_point: Optional[str] = None

    def add_node(self, name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.nodes[name] = fn

    def add_edge(self, from_node: str, to_node: str):
        self.edges[from_node] = to_node

    def add_conditional_edges(
        self,
        from_node: str,
        router_fn: Callable[[Dict[str, Any]], str],
        path_map: Dict[str, str]
    ):
        self.conditional_edges[from_node] = (router_fn, path_map)

    def set_entry_point(self, node_name: str):
        self.entry_point = node_name

    def compile(
        self,
        checkpointer: Optional[SqliteCheckpointer] = None,
        interrupt_before: Optional[List[str]] = None
    ) -> "CompiledGraph":
        return CompiledGraph(
            nodes=self.nodes,
            edges=self.edges,
            conditional_edges=self.conditional_edges,
            entry_point=self.entry_point,
            checkpointer=checkpointer,
            interrupt_before=interrupt_before or []
        )


class CompiledGraph:
    def __init__(
        self,
        nodes: Dict[str, Callable],
        edges: Dict[str, str],
        conditional_edges: Dict[str, tuple],
        entry_point: str,
        checkpointer: Optional[SqliteCheckpointer] = None,
        interrupt_before: Optional[List[str]] = None
    ):
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point
        self.checkpointer = checkpointer
        self.interrupt_before = set(interrupt_before or [])

    def invoke(self, initial_state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Starts a fresh workflow execution from the entry point."""
        thread_id = config.get("configurable", {}).get("thread_id", "default_thread")
        state = dict(initial_state)
        current_node = self.entry_point
        step_count = 0

        print("\n" + "=" * 70)
        print(f" WORKFLOW INITIATED [Thread: {thread_id}]")
        print("=" * 70)

        return self._run_loop(state=state, current_node=current_node, step_count=step_count, thread_id=thread_id)

    def resume(
        self,
        config: Dict[str, Any],
        state_patch: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Resumes a paused/interrupted workflow from its latest checkpoint."""
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id or not self.checkpointer:
            raise ValueError("Resuming requires an active checkpointer and a thread_id.")

        checkpoint = self.checkpointer.get_latest(thread_id)
        if not checkpoint:
            raise ValueError(f"No checkpoint found for thread_id '{thread_id}'.")

        state = checkpoint["state"]
        next_node = state.get("__next_node__")
        step_count = checkpoint["step_count"]

        if not next_node or next_node == END:
            print(f"[Engine] Thread '{thread_id}' is already finished or cannot be resumed.")
            return state

        # Apply Human Modifications or Approvals (supports dict or callable)
        if state_patch:
            if callable(state_patch):
                state_patch = state_patch()
            print(f"\n[Engine] Applying Human-In-The-Loop patch to State: {list(state_patch.keys())}")
            state.update(state_patch)

        # Clear interrupt marker to prevent immediate re-interruption on this node
        state["__interrupted__"] = False
        state.pop("__next_node__", None)

        print("\n" + "=" * 70)
        print(f" WORKFLOW RESUMED [Thread: {thread_id}] at Node: '{next_node}'")
        print("=" * 70)

        # Run starting directly from the resumed node, bypassing interrupt check for this step
        return self._run_loop(
            state=state,
            current_node=next_node,
            step_count=step_count,
            thread_id=thread_id,
            skip_interrupt_check_for_node=next_node
        )

    def _run_loop(
        self,
        state: Dict[str, Any],
        current_node: str,
        step_count: int,
        thread_id: str,
        skip_interrupt_check_for_node: Optional[str] = None
    ) -> Dict[str, Any]:
        max_steps = 15

        while current_node != END and step_count < max_steps:
            # Check for Human-In-The-Loop Breakpoint (interrupt_before)
            if current_node in self.interrupt_before and current_node != skip_interrupt_check_for_node:
                print(f"\n[!] [BREAKPOINT TRIGGERED] Execution paused BEFORE sensitive node: '{current_node}'")
                print(f"    Checkpointed state saved to SQLite database for Thread ID: '{thread_id}'.")
                print(f"    Workflow is waiting for Human-In-The-Loop review & authorization...")

                # Flag state as interrupted and record what needs to execute next
                state["__interrupted__"] = True
                state["__next_node__"] = current_node

                if self.checkpointer:
                    self.checkpointer.put(thread_id, step_count, f"INTERRUPT_BEFORE_{current_node}", state)

                return state

            # Clear one-time skip flag
            skip_interrupt_check_for_node = None

            step_count += 1
            print(f"\n>>> [Step {step_count}] Executing Node: '{current_node}'")

            node_fn = self.nodes.get(current_node)
            if not node_fn:
                raise ValueError(f"Node function '{current_node}' not registered.")

            state_patch = node_fn(state)
            if state_patch:
                state.update(state_patch)

            # Persist state after successful node execution
            if self.checkpointer:
                self.checkpointer.put(thread_id, step_count, current_node, state)

            # Determine Next Node via Conditional Edge or Direct Edge
            if current_node in self.conditional_edges:
                router_fn, path_map = self.conditional_edges[current_node]
                decision = router_fn(state)
                next_node = path_map.get(decision, END)
                print(f"    [Router Decision]: '{decision}' --> Next Node: '{next_node}'")
            elif current_node in self.edges:
                next_node = self.edges[current_node]
                print(f"    [Direct Edge]: '{current_node}' --> '{next_node}'")
            else:
                next_node = END

            current_node = next_node

        print("\n" + "=" * 70)
        print(f" WORKFLOW COMPLETED (Total Steps: {step_count})")
        print("=" * 70)
        return state


# =====================================================================
# 4. Use Case: Sensitive Database Migration & Incident Remediation
# =====================================================================

def incident_analyzer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Uses Gemini to analyze the incident and propose remediation SQL."""
    incident = state["incident_report"]
    print(f"    [Analyzer] Analyzing incident: '{incident['title']}'...")

    prompt = f"""You are a Principal Database Administrator and Site Reliability Engineer.
An incident alert occurred in production:
Title: {incident['title']}
Description: {incident['description']}
Table Impacted: {incident['table']}

Generate the SQL statement(s) required to fix this issue safely.
Return ONLY valid SQL statements. Do not include markdown fences, comments, or explanations."""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0)
    )

    clean_sql = response.text.replace("```sql", "").replace("```", "").strip()
    print(f"    [Analyzer] Generated Proposed SQL:\n    {clean_sql}")

    return {
        "proposed_sql": clean_sql,
        "status": "ANALYZED"
    }


def safety_auditor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates safety risks of proposed SQL (locks, destructive statements)."""
    sql = state["proposed_sql"].upper()
    print("    [Auditor] Inspecting SQL for safety hazards...")

    is_destructive = any(keyword in sql for keyword in ["DROP", "TRUNCATE", "DELETE", "CASCADE"])
    is_schema_alteration = any(keyword in sql for keyword in ["ALTER", "CREATE INDEX", "ADD COLUMN"])

    if is_destructive:
        risk_level = "CRITICAL"
        risk_reason = "Contains potentially destructive table or data modification commands."
    elif is_schema_alteration:
        risk_level = "HIGH"
        risk_reason = "DDL schema alteration may acquire exclusive table metadata locks."
    else:
        risk_level = "LOW"
        risk_reason = "Standard non-locking query or routine operation."

    print(f"    [Auditor] Assessed Risk Level: {risk_level} ({risk_reason})")

    return {
        "risk_level": risk_level,
        "risk_reason": risk_reason,
        "status": "AUDITED"
    }


def execute_migration_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """CRITICAL / SENSITIVE NODE: Applies migration to the target database.
    
    This node MUST be guarded by an interrupt_before gatekeeper so it never executes
    without human confirmation.
    """
    human_approval = state.get("human_approval")
    sql_to_run = state.get("proposed_sql")

    print("    [Migration Engine] Checking human authorization...")
    if human_approval != "APPROVED":
        raise PermissionError(f"UNAUTHORIZED ACCESS: Cannot execute migration. Approval status is '{human_approval}'")

    print("    [Migration Engine] Executing authorized DDL statements against production DB...")
    
    # Simulate DB execution in an in-memory SQLite sandbox
    test_db = sqlite3.connect(":memory:")
    test_db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, temp_token TEXT)")
    
    # Execute the generated statements
    try:
        test_db.executescript(sql_to_run)
        execution_receipt = "SUCCESS: Migration executed successfully. Zero query errors."
    except Exception as e:
        execution_receipt = f"EXECUTION FAILED: {str(e)}"
    finally:
        test_db.close()

    print(f"    [Migration Engine] {execution_receipt}")
    return {
        "execution_receipt": execution_receipt,
        "status": "EXECUTED"
    }


def rollback_or_abort_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Executed if human rejects or cancels the proposal."""
    reason = state.get("rejection_reason", "Human supervisor rejected migration.")
    print(f"    [Abort Handler] Migration ABORTED. Reason: {reason}")
    return {
        "execution_receipt": f"ABORTED: {reason}",
        "status": "ABORTED"
    }


def notification_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Notifies SRE channel of resolution."""
    print("    [Notifier] Broadcasting final incident receipt to Slack #incident-response...")
    summary = f"""
===========================================================================
                      INCIDENT REMEDIATION REPORT
===========================================================================
- Incident Title   : {state['incident_report']['title']}
- Risk Level       : {state.get('risk_level')}
- Human Decision   : {state.get('human_approval', 'PENDING')}
- Applied SQL      : {state.get('proposed_sql')}
- Execution Result : {state.get('execution_receipt')}
- Workflow Status  : {state.get('status')}
===========================================================================
"""
    return {"final_report": summary.strip()}


# =====================================================================
# 5. Routing Logic & Graph Assembly
# =====================================================================

def route_post_audit(state: Dict[str, Any]) -> str:
    """Routes based on human decision once resumed from breakpoint."""
    approval = state.get("human_approval")
    if approval == "REJECTED":
        return "abort"
    # Default path proceeds to execute migration
    return "proceed"


def human_review_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Human-in-the-loop review node.
    
    When execution is resumed, this node logs the human operator's verdict
    and passes it down to the conditional router.
    """
    decision = state.get("human_approval", "PENDING")
    reviewer = state.get("human_reviewer", "anonymous")
    print(f"    [Human Review Node] Recorded decision: '{decision}' by {reviewer}")
    return {"review_status": f"REVIEWED_{decision}"}


def build_hitl_workflow(checkpointer: SqliteCheckpointer) -> CompiledGraph:
    workflow = StateGraph()

    # 1. Register Nodes
    workflow.add_node("analyzer", incident_analyzer_node)
    workflow.add_node("auditor", safety_auditor_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("execute_migration", execute_migration_node)
    workflow.add_node("abort_migration", rollback_or_abort_node)
    workflow.add_node("notifier", notification_node)

    # 2. Entry Point
    workflow.set_entry_point("analyzer")

    # 3. Edges
    workflow.add_edge("analyzer", "auditor")
    workflow.add_edge("auditor", "human_review")
    
    # Conditional Router after human review / resume
    workflow.add_conditional_edges(
        from_node="human_review",
        router_fn=route_post_audit,
        path_map={
            "proceed": "execute_migration",
            "abort": "abort_migration"
        }
    )

    workflow.add_edge("execute_migration", "notifier")
    workflow.add_edge("abort_migration", "notifier")
    workflow.add_edge("notifier", END)

    # 4. Compile with SQLite Checkpointer AND HITL Breakpoint!
    # Execution will strictly PAUSE before entering 'human_review'
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"]
    )


# =====================================================================
# 6. Demonstration: Pause, Inspect DB, Human Intervention, Resume
# =====================================================================
if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(__file__), "workflow_checkpoints.db")
    checkpointer = SqliteCheckpointer(db_path=db_file)
    graph = build_hitl_workflow(checkpointer)

    THREAD_ID = f"incident-ticket-{datetime.datetime.now().strftime('%H%M%S')}"
    config = {"configurable": {"thread_id": THREAD_ID}}

    initial_state = {
        "incident_report": {
            "title": "Severe latency on user login queries",
            "description": "Slow query logs indicate full table scans on users table for email lookup. Also need to drop unused legacy column temp_token.",
            "table": "users"
        },
        "status": "INITIATED"
    }

    # -------------------------------------------------------------
    # PHASE 1: Run workflow until the sensitive breakpoint
    # -------------------------------------------------------------
    print("\n>>> PHASE 1: Running autonomous workflow until human checkpoint...")
    paused_state = graph.invoke(initial_state, config=config)

    print(f"\nState after invocation pause: Interrupted={paused_state.get('__interrupted__')}")
    print(f"Pending Next Node: '{paused_state.get('__next_node__')}'")

    # -------------------------------------------------------------
    # PHASE 2: Checkpoint Inspection (Simulating DB Audit & Review)
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> PHASE 2: Inspecting Checkpoints Database (Audit Trail)")
    print("-" * 70)
    history = checkpointer.list_history(THREAD_ID)
    for entry in history:
        print(f"  [Checkpoint #{entry['checkpoint_id']}] Step: {entry['step_count']} | Node: '{entry['node_name']}' | Time: {entry['created_at']}")

    latest = checkpointer.get_latest(THREAD_ID)
    print(f"\n[Human Review Dashboard]")
    print(f"  Incident  : {latest['state']['incident_report']['title']}")
    print(f"  Risk Level: {latest['state'].get('risk_level')}")
    print(f"  Proposed SQL by AI:")
    print(f"  ---> {latest['state'].get('proposed_sql')}")

    # -------------------------------------------------------------
    # PHASE 3: Human Decision & Resume
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> PHASE 3: Simulating Human Review & Workflow Resumption")
    print("-" * 70)
    
    # The human can:
    # 1. Approve as-is or modify SQL (e.g. human_approval = "APPROVED")
    # 2. Reject the proposal (e.g. human_approval = "REJECTED") -> routes to abort_migration
    human_patch = {
        "human_approval": "REJECTED",
        "human_reviewer": "sarah.connor@sre-team.internal",
        "proposed_sql": "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email); ALTER TABLE users DROP COLUMN temp_token;"
    }

    print(f"\n[Human Operator Decision]: Decision='{human_patch['human_approval']}' by {human_patch['human_reviewer']}")
    if human_patch["human_approval"] == "APPROVED":
        print("  -> Modifying SQL slightly for production index naming & approving!")
    else:
        print("  -> Rejecting migration proposal!")

    # Resume the workflow using the thread_id
    final_state = graph.resume(config=config, state_patch=human_patch)

    print("\n" + final_state.get("final_report", "No final report generated."))
