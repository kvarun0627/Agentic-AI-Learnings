import os
import json
from typing import Dict, Any, Callable, List, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

# =====================================================================
# Setup & Client Initialization
# =====================================================================
# Load .env from root workspace if present
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.5-flash-lite"


# =====================================================================
# 1. Pure-Python StateGraph Engine (The Foundation of LangGraph)
# =====================================================================
END = "__END__"
START = "__START__"


class StateGraph:
    """A lightweight, deterministic state machine graph engine.
    
    Nodes represent discrete processing steps (functions taking state and returning updates).
    Edges define deterministic or conditional transitions between nodes.
    """
    def __init__(self):
        self.nodes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.edges: Dict[str, str] = {}
        self.conditional_edges: Dict[str, tuple[Callable[[Dict[str, Any]], str], Dict[str, str]]] = {}
        self.entry_point: Optional[str] = None

    def add_node(self, name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]):
        if name in self.nodes:
            raise ValueError(f"Node '{name}' already exists.")
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
        if node_name not in self.nodes:
            raise ValueError(f"Entry point '{node_name}' is not a registered node.")
        self.entry_point = node_name

    def compile(self):
        if not self.entry_point:
            raise ValueError("Cannot compile graph without an entry point. Call set_entry_point().")
        return CompiledGraph(
            nodes=self.nodes,
            edges=self.edges,
            conditional_edges=self.conditional_edges,
            entry_point=self.entry_point
        )


class CompiledGraph:
    def __init__(
        self,
        nodes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
        edges: Dict[str, str],
        conditional_edges: Dict[str, tuple[Callable[[Dict[str, Any]], str], Dict[str, str]]],
        entry_point: str
    ):
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point

    def invoke(self, initial_state: Dict[str, Any], max_steps: int = 15) -> Dict[str, Any]:
        """Executes the workflow graph starting from the entry point until reaching END."""
        state = dict(initial_state)
        current_node = self.entry_point
        step_count = 0

        print("\n" + "=" * 70)
        print(" GRAPH EXECUTION STARTED")
        print(f" Entry Node: '{current_node}'")
        print("=" * 70)

        while current_node != END and step_count < max_steps:
            step_count += 1
            print(f"\n>>> [Step {step_count}] Executing Node: '{current_node}'")
            node_fn = self.nodes.get(current_node)
            if not node_fn:
                raise RuntimeError(f"Node function '{current_node}' not found.")

            # 1. Execute Node and obtain state patch/delta
            state_update = node_fn(state)
            if state_update and isinstance(state_update, dict):
                state.update(state_update)
                print(f"    State keys updated: {list(state_update.keys())}")

            # 2. Determine Next Node (Conditional Edge vs Direct Edge)
            if current_node in self.conditional_edges:
                router_fn, path_map = self.conditional_edges[current_node]
                decision = router_fn(state)
                next_node = path_map.get(decision)
                if not next_node:
                    raise RuntimeError(
                        f"Router from '{current_node}' returned decision '{decision}', "
                        f"which is not mapped in {list(path_map.keys())}"
                    )
                print(f"    [Router Decision]: '{decision}' -> Next Node: '{next_node}'")
            elif current_node in self.edges:
                next_node = self.edges[current_node]
                print(f"    [Direct Edge]: '{current_node}' -> '{next_node}'")
            else:
                print(f"    [No Edge Specified]: Terminating workflow.")
                next_node = END

            current_node = next_node

        print("\n" + "=" * 70)
        print(" GRAPH EXECUTION FINISHED (Reached END)")
        print(f" Total Steps Executed: {step_count}")
        print("=" * 70)
        return state


# =====================================================================
# 2. Enterprise Incident Triage Workflow Implementation
# =====================================================================

# --- Node 1: Triage & Classification ---
def triage_node(state: Dict[str, Any]) -> Dict[str, Any]:
    raw_alert = state["raw_alert"]
    prompt = f"""You are an automated SRE Triage classifier.
Analyze this incident alert:
\"{raw_alert}\"

Return ONLY a valid JSON object with these keys:
- "category": exactly one of ["SECURITY", "PERFORMANCE", "GENERAL"]
- "severity": exactly one of ["CRITICAL", "HIGH", "LOW"]
- "summary": one sentence summary of the issue
"""
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0
        )
    )
    parsed = json.loads(response.text.strip())
    return {
        "category": parsed.get("category", "GENERAL").upper(),
        "severity": parsed.get("severity", "HIGH").upper(),
        "triage_summary": parsed.get("summary", "")
    }


# --- Conditional Router: Based on Category ---
def route_incident(state: Dict[str, Any]) -> str:
    category = state.get("category", "GENERAL")
    if category == "SECURITY":
        return "to_security"
    elif category == "PERFORMANCE":
        return "to_performance"
    return "to_general"


# --- Node 2A: Security Specialist Node ---
def security_handler_node(state: Dict[str, Any]) -> Dict[str, Any]:
    alert = state["raw_alert"]
    summary = state.get("triage_summary", "")
    prompt = f"""You are a Cloud Security Incident Responder.
Security Issue: {summary}
Full Alert: {alert}

Provide 2-3 immediate containment actions as a bulleted list.
Actions must include firewall, IP blocking, or credential revocation steps."""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0)
    )
    return {
        "containment_strategy": response.text.strip(),
        "quarantine_status": "ACTIVE_ISOLATION"
    }


# --- Node 2B: Performance Specialist Node ---
def performance_handler_node(state: Dict[str, Any]) -> Dict[str, Any]:
    alert = state["raw_alert"]
    summary = state.get("triage_summary", "")
    prompt = f"""You are a Systems Performance Engineer.
Performance Issue: {summary}
Full Alert: {alert}

Provide 2-3 immediate mitigation actions (e.g. horizontal pod autoscaling, rate limiting, cache flushing)."""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0)
    )
    return {
        "containment_strategy": response.text.strip(),
        "quarantine_status": "SCALED_AND_THROTTLED"
    }


# --- Node 2C: General Triage Node ---
def general_handler_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "containment_strategy": "Escalated to on-call tier 1 support for manual inspection.",
        "quarantine_status": "MONITORING_ONLY"
    }


# --- Node 3: Compliance & Final Audit Reporter (Convergence Point) ---
def compliance_reporting_node(state: Dict[str, Any]) -> Dict[str, Any]:
    report = f"""
===========================================================================
               INCIDENT RESPONSE AUDIT & COMPLIANCE TICKET
===========================================================================
- Incident ID         : {state.get("incident_id")}
- Classification      : {state.get("category")} (Severity: {state.get("severity")})
- Triage Summary      : {state.get("triage_summary")}
- Quarantine Status   : {state.get("quarantine_status")}
- Recommended Actions :
{state.get("containment_strategy")}
===========================================================================
"""
    return {"final_audit_report": report.strip()}


# =====================================================================
# 3. Assemble and Compile the Graph
# =====================================================================
def build_incident_workflow() -> CompiledGraph:
    workflow = StateGraph()

    # 1. Register Nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("security_handler", security_handler_node)
    workflow.add_node("performance_handler", performance_handler_node)
    workflow.add_node("general_handler", general_handler_node)
    workflow.add_node("compliance_reporter", compliance_reporting_node)

    # 2. Define Entry Point
    workflow.set_entry_point("triage")

    # 3. Define Conditional Routing from Triage
    workflow.add_conditional_edges(
        from_node="triage",
        router_fn=route_incident,
        path_map={
            "to_security": "security_handler",
            "to_performance": "performance_handler",
            "to_general": "general_handler"
        }
    )

    # 4. Define Convergence Edges (All handlers route to compliance_reporter)
    workflow.add_edge("security_handler", "compliance_reporter")
    workflow.add_edge("performance_handler", "compliance_reporter")
    workflow.add_edge("general_handler", "compliance_reporter")

    # 5. Terminal Edge
    workflow.add_edge("compliance_reporter", END)

    return workflow.compile()


# =====================================================================
# 4. Test Runs with Different Incident Types
# =====================================================================
if __name__ == "__main__":
    app = build_incident_workflow()

    # Test Case 1: Security Incident (Should route: triage -> security_handler -> compliance_reporter -> END)
    print("\n\n" + "#" * 80)
    print(" TEST RUN 1: SECURITY ALERT")
    print("#" * 80)
    incident_1 = {
        "incident_id": "INC-8801",
        "raw_alert": "CRITICAL: Multiple failed SSH root logins from unknown IP 198.51.100.23 on bastion-prod-01. Port scan detected."
    }
    result_1 = app.invoke(incident_1)
    print("\n[FINAL OUTPUT FOR INCIDENT 1]:")
    print(result_1["final_audit_report"])

    # Test Case 2: Performance Incident (Should route: triage -> performance_handler -> compliance_reporter -> END)
    print("\n\n" + "#" * 80)
    print(" TEST RUN 2: PERFORMANCE ALERT")
    print("#" * 80)
    incident_2 = {
        "incident_id": "INC-8802",
        "raw_alert": "WARN: High CPU utilization (98%) on payment-worker-pool-2 due to sudden spike in checkout traffic."
    }
    result_2 = app.invoke(incident_2)
    print("\n[FINAL OUTPUT FOR INCIDENT 2]:")
    print(result_2["final_audit_report"])
