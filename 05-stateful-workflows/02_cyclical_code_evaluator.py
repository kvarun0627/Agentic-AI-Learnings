
import os
import re
import traceback
from typing import Dict, Any, Callable, Optional
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
# 2. Reusing Our StateGraph Engine from Lab 01
# (Notice how this same engine supports CYCLES with zero changes!)
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

    def compile(self) -> "CompiledGraph":
        return CompiledGraph(self.nodes, self.edges, self.conditional_edges, self.entry_point)


class CompiledGraph:
    def __init__(self, nodes, edges, conditional_edges, entry_point):
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point

    def invoke(self, initial_state: Dict[str, Any], max_steps: int = 15) -> Dict[str, Any]:
        state = dict(initial_state)
        current_node = self.entry_point
        step_count = 0

        print("\n" + "=" * 70)
        print(" CYCLICAL GRAPH EXECUTION STARTED")
        print(f" Task: {state.get('task')}")
        print("=" * 70)

        while current_node != END and step_count < max_steps:
            step_count += 1
            print(f"\n>>> [Step {step_count}] Executing Node: '{current_node}'")

            node_fn = self.nodes.get(current_node)
            state_patch = node_fn(state)
            if state_patch:
                state.update(state_patch)

            # Determine next node via Conditional Edge or Direct Edge
            if current_node in self.conditional_edges:
                router_fn, path_map = self.conditional_edges[current_node]
                decision = router_fn(state)
                next_node = path_map.get(decision)
                print(f"    [Router Decision]: '{decision}' --> Next Node: '{next_node}'")
            elif current_node in self.edges:
                next_node = self.edges[current_node]
                print(f"    [Direct Edge]: '{current_node}' --> '{next_node}'")
            else:
                next_node = END

            current_node = next_node

        print("\n" + "=" * 70)
        print(f" WORKFLOW FINISHED (Total Steps: {step_count})")
        print("=" * 70)
        return state


# =====================================================================
# 3. Nodes (Generator, Validator, Publisher, Escalation)
# =====================================================================

def clean_python_code(raw_response: str) -> str:
    """Extracts raw python code from markdown code fences if present."""
    match = re.search(r"```python\s*(.*?)\s*```", raw_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(.*?)\s*```", raw_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_response.strip()


# NODE 1: The Code Generator / Refiner
def code_generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    task = state["task"]
    iteration = state.get("iteration", 0) + 1
    last_error = state.get("error_feedback")

    if not last_error:
        # First attempt: Write code from scratch
        print(f"    [Generator] Writing initial implementation (Attempt {iteration})...")
        prompt = f"""You are an expert Python engineer.
Task: {task}

Write ONLY the Python function. Do NOT include markdown explanations, markdown code blocks, or usage examples.
Just raw Python code for the function."""
    else:
        # Self-correction attempt: Fix the code using the test failure feedback!
        print(f"    [Generator] Self-Correcting Code based on Test Error (Attempt {iteration})...")
        prompt = f"""You are an expert Python engineer.
Task: {task}

Your previous code implementation failed the automated unit tests!
-----------------------------------------------------------------
PREVIOUS CODE:
{state['code']}
-----------------------------------------------------------------
TEST FAILURE / TRACEBACK:
{last_error}
-----------------------------------------------------------------

Analyze the failure carefully. Fix the bug so that all edge cases pass.
Write ONLY the corrected Python function. Do NOT include explanations."""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0)
    )

    clean_code = clean_python_code(response.text)
    return {
        "code": clean_code,
        "iteration": iteration
    }


# NODE 2: The Code Tester (Real Unit Test Execution via Python exec)
def code_tester_node(state: Dict[str, Any]) -> Dict[str, Any]:
    code = state["code"]
    print(f"    [Tester] Running automated test suite against generated code...")

    # Define test suite expectations
    test_suite_code = """
# Test 1: Standard happy path
res1 = parse_user_scores(["alice:90", "bob:85"])
assert res1 == {"alice": 90, "bob": 85}, f"Test 1 Failed: Expected {{'alice': 90, 'bob': 85}}, got {res1}"

# Test 2: Whitespace trimming
res2 = parse_user_scores(["  charlie : 100  "])
assert res2 == {"charlie": 100}, f"Test 2 Failed: Whitespace not handled properly, got {res2}"

# Test 3: Invalid score should be skipped without throwing exception
res3 = parse_user_scores(["david:not_a_number", "eve:75"])
assert res3 == {"eve": 75}, f"Test 3 Failed: Non-numeric score not skipped, got {res3}"

# Test 4: Tricky edge cases: missing colon, empty string, None in list
res4 = parse_user_scores(["", "bad_format", None, "frank:50"])
assert res4 == {"frank": 50}, f"Test 4 Failed: Corrupt entries caused crash, got {res4}"
"""

    execution_namespace: Dict[str, Any] = {}
    try:
        # Compile and execute the generated function into our isolated namespace
        exec(code, execution_namespace)

        if "parse_user_scores" not in execution_namespace:
            raise AssertionError("Function 'parse_user_scores' was not defined in the code.")

        # Run the unit test assertions
        exec(test_suite_code, execution_namespace)

        print("    [Tester] All 4 unit tests PASSED successfully!")
        return {
            "test_status": "PASSED",
            "error_feedback": None
        }

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"    [Tester] Test FAILED: {error_msg}")
        return {
            "test_status": "FAILED",
            "error_feedback": error_msg
        }


# NODE 3: Production Publisher (Reached only if tests pass)
def publisher_node(state: Dict[str, Any]) -> Dict[str, Any]:
    print("    [Publisher] Code verified and ready for deployment!")
    result_card = f"""
===========================================================================
                 VERIFIED CODE ARTIFACT (PASSED CI/CD)
===========================================================================
- Task                  : {state['task']}
- Total Iterations Taken: {state['iteration']}
- Final Code:
{state['code']}
===========================================================================
"""
    return {"final_output": result_card.strip()}


# NODE 4: Escalation Node (Reached if max retries exceeded)
def escalation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    print("    [Escalation] Maximum retries exceeded. Alerting human developer...")
    return {
        "final_output": f"ESCALATION: Code generation failed after {state['iteration']} attempts. Last error: {state.get('error_feedback')}"
    }


# =====================================================================
# 4. The Cyclical Conditional Edge (The Loop Logic)
# =====================================================================

MAX_RETRIES = 3

def check_test_results_and_route(state: Dict[str, Any]) -> str:
    """The key router: Decides whether to proceed to Publisher, or LOOP BACK to Generator!"""
    status = state.get("test_status")
    iteration = state.get("iteration", 0)

    if status == "PASSED":
        return "approved"  # Route to Publisher
    
    # If failed, check retry counter
    if iteration < MAX_RETRIES:
        return "retry"     # LOOP BACK to Generator! (The Cycle)
    else:
        return "give_up"   # Route to Escalation


# =====================================================================
# 5. Graph Wiring & Compilation
# =====================================================================

def build_cyclical_code_graph() -> CompiledGraph:
    workflow = StateGraph()

    # Register Nodes
    workflow.add_node("generator", code_generator_node)
    workflow.add_node("tester", code_tester_node)
    workflow.add_node("publisher", publisher_node)
    workflow.add_node("escalation", escalation_node)

    # Entry Point
    workflow.set_entry_point("generator")

    # Edge 1: Generator always goes to Tester
    workflow.add_edge("generator", "tester")

    # Edge 2: THE CYCLICAL CONDITIONAL EDGE!
    # Tester routes to:
    # - "publisher" if passed
    # - "generator" if failed (LOOP BACK!)
    # - "escalation" if retries exceeded
    workflow.add_conditional_edges(
        from_node="tester",
        router_fn=check_test_results_and_route,
        path_map={
            "approved": "publisher",
            "retry": "generator",      # <-- THE BACKWARD EDGE (CYCLE)
            "give_up": "escalation"
        }
    )

    # Terminal Edges
    workflow.add_edge("publisher", END)
    workflow.add_edge("escalation", END)

    return workflow.compile()


# =====================================================================
# 6. Execute the Cyclical Workflow
# =====================================================================
if __name__ == "__main__":
    task_description = (
        "Write a Python function called 'parse_user_scores(raw_data: list[str]) -> dict[str, int]' "
        "that parses a list of strings formatted as 'username:score'. "
        "It must strip whitespace, skip empty items or items with invalid scores, "
        "and handle None values gracefully without crashing."
    )

    initial_state = {
        "task": task_description,
        "iteration": 0,
        "code": None,
        "test_status": None,
        "error_feedback": None
    }

    graph = build_cyclical_code_graph()
    result = graph.invoke(initial_state)

    print("\n" + result["final_output"])
