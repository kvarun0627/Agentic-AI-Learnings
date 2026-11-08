import os
import math
from typing import List, Dict, Any
from dotenv import load_dotenv
from google import genai
from google.genai import types

# =====================================================================
# Setup & Client Initialization
# =====================================================================
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.5-flash-lite"
EMBEDDING_MODEL = "gemini-embedding-001"


# =====================================================================
# 1. Vector Store (Long-Term Knowledge Memory)
# =====================================================================
def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot_product / (mag_a * mag_b)


class InMemoryVectorStore:
    def __init__(self, client: genai.Client, model: str):
        self.client = client
        self.model = model
        self.documents: List[Dict[str, Any]] = []

    def _embed(self, text: str) -> List[float]:
        resp = self.client.models.embed_content(model=self.model, contents=text)
        return resp.embeddings[0].values

    def add_document(self, doc_id: str, title: str, content: str):
        emb = self._embed(content)
        self.documents.append({"id": doc_id, "title": title, "content": content, "embedding": emb})

    def search(self, query: str, top_k: int = 1) -> List[Dict[str, Any]]:
        query_vec = self._embed(query)
        scored = []
        for d in self.documents:
            score = cosine_similarity(query_vec, d["embedding"])
            scored.append({"id": d["id"], "title": d["title"], "content": d["content"], "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


# Initialize & Seed the Knowledge Base with DevOps Runbooks
runbook_store = InMemoryVectorStore(client=client, model=EMBEDDING_MODEL)
runbook_store.add_document(
    doc_id="RB-001",
    title="PostgreSQL Connection Pool Starvation",
    content="Symptoms: HikariCP connection timeouts, HTTP 503 errors on database calls. "
            "Root Cause: Leaked connections or pool capacity too low for traffic. "
            "Remediation: Set pool size to 50 via action='scale_db_pool' with parameter pool_size=50."
)
runbook_store.add_document(
    doc_id="RB-002",
    title="Redis Cache Out of Memory",
    content="Symptoms: Command 'OOM command not allowed when used memory > maxmemory'. "
            "Root Cause: Keys written without TTL or allkeys-lru eviction disabled. "
            "Remediation: Set eviction policy to allkeys-lru via action='set_redis_policy' with policy='allkeys-lru'."
)
runbook_store.add_document(
    doc_id="RB-003",
    title="Kubernetes Pod CrashLoopBackOff",
    content="Symptoms: Pod restarts continuously with exit code 137 (OOMKilled). "
            "Root Cause: JVM heap exceeds container cgroup limits. "
            "Remediation: Increase memory limit to 2Gi via action='scale_pod_memory' with limit='2Gi'."
)


# =====================================================================
# 2. Simulated Infrastructure State & Live Tools
# =====================================================================
INFRA_STATE = {
    "payment-service": {
        "status": "CRITICAL",
        "error_log": "ConnectionTimeoutException: HikariPool-1 - Connection is not available, request timed out after 30005ms. HTTP 503.",
        "config": {"db_pool_size": 10, "max_idle": 5}
    }
}


def search_runbooks(query: str) -> dict:
    """Performs semantic vector search across engineering runbooks and incident recovery manuals.
    
    Args:
        query: Problem description or symptoms (e.g. 'HikariCP timeout', 'database pool empty')
    """
    print(f"    [TOOL EXECUTING] search_runbooks(query='{query}')")
    matches = runbook_store.search(query=query, top_k=1)
    if not matches:
        return {"error": "No matching runbooks found."}
    match = matches[0]
    return {
        "match_id": match["id"],
        "title": match["title"],
        "relevance_score": round(match["score"], 4),
        "official_remediation_guide": match["content"]
    }


def get_service_logs(service_name: str) -> dict:
    """Fetches the latest error logs and status for a failing microservice.
    
    Args:
        service_name: The microservice name (e.g. 'payment-service')
    """
    print(f"    [TOOL EXECUTING] get_service_logs(service_name='{service_name}')")
    svc = INFRA_STATE.get(service_name)
    if not svc:
        return {"error": f"Unknown service '{service_name}'"}
    return {
        "service": service_name,
        "status": svc["status"],
        "latest_error": svc["error_log"],
        "current_config": svc["config"]
    }


def apply_remediation(service_name: str, action: str, parameter: str) -> dict:
    """Applies an operational fix to a service based on approved runbook instructions.
    
    Args:
        service_name: Microservice to patch (e.g. 'payment-service')
        action: Remediation action name from the runbook (e.g. 'scale_db_pool')
        parameter: New parameter value (e.g. '50')
    """
    print(f"    [TOOL EXECUTING] apply_remediation(service='{service_name}', action='{action}', param='{parameter}')")
    svc = INFRA_STATE.get(service_name)
    if not svc:
        return {"error": f"Unknown service '{service_name}'"}
    
    if action == "scale_db_pool":
        svc["config"]["db_pool_size"] = int(parameter)
        svc["status"] = "HEALTHY"
        svc["error_log"] = "None. All connections healthy."
        return {
            "status": "SUCCESS",
            "message": f"Successfully scaled {service_name} db_pool_size to {parameter}. Service is now HEALTHY."
        }
    return {"status": "FAILED", "error": f"Unsupported action '{action}'"}


# Tool mapping table
TOOL_FUNCTIONS = {
    "search_runbooks": search_runbooks,
    "get_service_logs": get_service_logs,
    "apply_remediation": apply_remediation
}


# =====================================================================
# 3. Autonomous RAG-Enabled ReAct Agent
# =====================================================================
SYSTEM_INSTRUCTION = """You are an Autonomous Site Reliability Engineering (SRE) Agent.
When an incident is reported:
1. Investigate the failing service logs using `get_service_logs`.
2. NEVER guess or hallucinate solutions. Search the company knowledge base using `search_runbooks` with the observed symptoms.
3. Apply the exact verified remediation using `apply_remediation` as instructed in the runbook.
4. Provide a concise post-mortem report once the service is healthy."""


def run_rag_agent(incident_alert: str):
    print("=" * 75)
    print(" INCIDENT TRIGGERED:")
    print(f" \"{incident_alert}\"")
    print("=" * 75)

    contents: List[types.Content] = [
        types.Content(role="user", parts=[types.Part.from_text(text=incident_alert)])
    ]

    tools_spec = [types.Tool(function_declarations=[
        types.FunctionDeclaration.from_callable(client=client, callable=fn)
        for fn in TOOL_FUNCTIONS.values()
    ])]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.0,
        tools=tools_spec
    )

    max_steps = 6
    step = 1

    while step <= max_steps:
        print(f"\n--- [Cycle {step}] Agent Thinking & Decision ---")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config
        )

        if response.text:
            print(f"    [Agent thought]: {response.text.strip()}")

        candidate = response.candidates[0]
        model_content = candidate.content
        contents.append(model_content)

        # Check if the model decided to call tools
        function_calls = [p.function_call for p in model_content.parts if p.function_call]

        if not function_calls:
            # Agent finished reasoning and produced final post-mortem
            print("\n" + "=" * 75)
            print(" AGENT POST-MORTEM & RESOLUTION REPORT:")
            print("=" * 75)
            print(response.text.strip())
            break

        # Execute tools called by the model
        tool_response_parts = []
        for fc in function_calls:
            fn_name = fc.name
            fn_args = dict(fc.args) if fc.args else {}
            
            tool_fn = TOOL_FUNCTIONS.get(fn_name)
            if not tool_fn:
                tool_output = {"error": f"Tool '{fn_name}' does not exist."}
            else:
                tool_output = tool_fn(**fn_args)

            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fn_name,
                    response={"result": tool_output}
                )
            )

        # Feed the tool observations back into the agent conversation
        contents.append(types.Content(role="user", parts=tool_response_parts))
        step += 1


if __name__ == "__main__":
    alert = "ALERT: P1 Incident on payment-service. Checkout API is timing out and throwing 503 errors under load."
    run_rag_agent(alert)
