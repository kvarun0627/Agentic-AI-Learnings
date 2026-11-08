import os
import sys
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Ensure UTF-8 output across Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# =====================================================================
# 1. Environment & Setup
# =====================================================================
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.5-flash-lite"
END = "__END__"


# =====================================================================
# 2. Worker Domain Tools (Specialized Capabilities)
# =====================================================================

# --- DB Specialist Mock Tools ---
def inspect_database_metrics() -> str:
    """Returns database connection pool utilization and active locks."""
    return json.dumps({
        "status": "CRITICAL",
        "active_connections": 498,
        "max_connections": 500,
        "waiting_threads": 142,
        "connection_pool_saturation": "99.6%",
        "active_deadlocks": 1
    })

def find_slow_queries_and_locks() -> str:
    """Returns queries holding exclusive locks causing connection starvation."""
    return json.dumps({
        "blocking_transaction_id": "TX_99482",
        "locked_table": "payment_transactions",
        "lock_type": "EXCLUSIVE_ROW_LOCK",
        "query": "SELECT * FROM payment_transactions WHERE status = 'PENDING' FOR UPDATE;",
        "running_seconds": 920,
        "impact": "Holding 140+ dependent checkout requests in pool wait queue"
    })

def terminate_blocking_transaction(tx_id: str) -> str:
    """Terminates a runaway transaction to release locks and free connections."""
    if tx_id == "TX_99482":
        return json.dumps({
            "status": "SUCCESS",
            "message": f"Transaction {tx_id} forcefully terminated. Exclusive locks released.",
            "connections_freed": 142
        })
    return json.dumps({"status": "FAILED", "error": f"Transaction {tx_id} not found."})


# --- Network Specialist Mock Tools ---
def test_payment_gateway_latency() -> str:
    """Pings external third-party payment gateway (Stripe/PayPal endpoint)."""
    return json.dumps({
        "gateway_endpoint": "https://api.stripe.com/v1/health",
        "latency_ms": 32,
        "packet_loss": "0.0%",
        "status": "HEALTHY",
        "verdict": "Third-party payment gateway is fully operational. Latency is normal."
    })

def inspect_ingress_traffic() -> str:
    """Inspects ingress load balancer for DDoS or traffic anomalies."""
    return json.dumps({
        "current_requests_per_sec": 1250,
        "expected_requests_per_sec": 1200,
        "ddos_anomaly_detected": False,
        "http_504_gateway_timeout_rate": "78.4%",
        "verdict": "504 timeouts are generated internally by backend services timing out, not incoming traffic spikes."
    })


# --- Infrastructure Specialist Mock Tools ---
def get_service_pod_health() -> str:
    """Returns CPU, Memory, and Pod health of the payment-service deployment."""
    return json.dumps({
        "deployment": "payment-service",
        "desired_replicas": 6,
        "ready_replicas": 2,
        "unhealthy_replicas": 4,
        "reason": "OOMKilled / Readiness probe failures due to blocked connection threads",
        "avg_cpu_percent": 94.2,
        "avg_memory_percent": 91.0
    })

def rolling_restart_service(deployment_name: str) -> str:
    """Performs a rolling restart of unhealthy service pods."""
    return json.dumps({
        "status": "SUCCESS",
        "deployment": deployment_name,
        "action": "Rolling restart triggered",
        "ready_replicas": "6/6",
        "avg_cpu_percent": 18.5,
        "avg_memory_percent": 24.1,
        "message": f"Deployment '{deployment_name}' successfully stabilized and responding to healthchecks."
    })


# =====================================================================
# 3. Structured Output Schema for Supervisor Decisions
# =====================================================================
class SupervisorDecision(BaseModel):
    reasoning: str = Field(description="Step-by-step diagnostic reasoning explaining what is currently known and what needs investigation next.")
    next_worker: str = Field(description="Next agent to invoke: 'DB_SPECIALIST', 'NETWORK_SPECIALIST', 'INFRA_SPECIALIST', or 'FINISH'.")
    instruction: str = Field(description="Specific, targeted instruction for the selected worker explaining what to investigate or execute.")


# =====================================================================
# 4. Specialist Worker Agents
# =====================================================================

class DatabaseSpecialistAgent:
    """Worker agent specialized exclusively in database queries, connections, and locks."""
    NAME = "DB_SPECIALIST"

    def execute(self, instruction: str) -> str:
        print(f"\n   [DB Specialist] Received order: '{instruction}'")
        
        # Check for mutation/remediation actions first
        if any(kw in instruction.lower() for kw in ["terminate", "kill", "cancel", "abort", "clear"]):
            result = terminate_blocking_transaction("TX_99482")
            print("   [DB Specialist] Action Taken: Killed blocking transaction TX_99482.")
            return f"Database Remediation Result: {result}"
        else:
            metrics = inspect_database_metrics()
            slow = find_slow_queries_and_locks()
            findings = f"Database Metrics: {metrics}\nSlow Query Analysis: {slow}"
            print("   [DB Specialist] Diagnosis: Found runaway TX_99482 saturating 99.6% of connections!")
            return findings


class NetworkSpecialistAgent:
    """Worker agent specialized exclusively in gateways, routes, and external dependencies."""
    NAME = "NETWORK_SPECIALIST"

    def execute(self, instruction: str) -> str:
        print(f"\n   [Network Specialist] Received order: '{instruction}'")
        
        gateway_health = test_payment_gateway_latency()
        ingress_status = inspect_ingress_traffic()
        print("   [Network Specialist] Diagnosis: External gateway is healthy. Issue is internal backend timeouts.")
        return f"Gateway Latency Check: {gateway_health}\nIngress Traffic Check: {ingress_status}"


class InfraSpecialistAgent:
    """Worker agent specialized in pod health, CPU/memory, and rolling restarts."""
    NAME = "INFRA_SPECIALIST"

    def execute(self, instruction: str) -> str:
        print(f"\n   [Infra Specialist] Received order: '{instruction}'")
        
        if "restart" in instruction.lower() or "scale" in instruction.lower() or "recover" in instruction.lower():
            restart_res = rolling_restart_service("payment-service")
            print("   [Infra Specialist] Action Taken: Executed rolling restart of payment-service.")
            return f"Pod Restart Result: {restart_res}"
        else:
            pod_health = get_service_pod_health()
            print("   [Infra Specialist] Diagnosis: 4 out of 6 pods unhealthy due to thread starvation.")
            return f"Infrastructure Health: {pod_health}"


# =====================================================================
# 5. The Supervisor Agent (The Orchestrator)
# =====================================================================

class IncidentSupervisorAgent:
    """Central Orchestrator / Incident Commander.
    
    Evaluates incident report and findings accumulated so far on the shared blackboard.
    Determines next worker to dispatch or signals FINISH when remediation is complete.
    """

    def decide(self, incident: Dict[str, Any], blackboard: List[Dict[str, str]]) -> SupervisorDecision:
        system_prompt = """You are the Lead SRE Incident Commander running a critical production incident triage.
Your job is to orchestrate specialized worker agents to diagnose and fix the incident as fast as possible.

Available Workers:
1. 'DB_SPECIALIST': Investigates database connection pools, table locks, slow queries, and terminates hung transactions.
2. 'NETWORK_SPECIALIST': Checks external payment gateway health, DNS, and ingress load balancer 504 errors.
3. 'INFRA_SPECIALIST': Checks Kubernetes pod CPU/memory and triggers rolling restarts of hung services.
4. 'FINISH': Only select this when the root cause has been diagnosed, remediated, and services are healthy.

Protocol:
- Step 1: Diagnose root cause (check Network or Database or Pods).
- Step 2: Once root cause is found (e.g. database locks), order the specialist to fix it.
- Step 3: If pods are hung after DB fix, order Infra Specialist to restart them.
- Step 4: When all systems report healthy, select 'FINISH'."""

        # Format incident & blackboard history
        history_text = "\n".join([f"- [{item['sender']}]: {item['content']}" for item in blackboard])
        if not history_text:
            history_text = "No investigations started yet."

        user_content = f"""Incident Summary:
Title: {incident['title']}
Description: {incident['description']}
Affected Service: {incident['service']}

Blackboard of Findings & Actions Taken So Far:
{history_text}

Analyze the latest state of the incident. What is the next logical action?"""

        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=SupervisorDecision
                )
            )
            return SupervisorDecision.model_validate_json(response.text)
        except Exception as e:
            # Fallback deterministic supervisor logic for offline/air-gapped testing
            print(f"   [!] Supervisor LLM fallback ({e})")
            return self._heuristic_fallback(blackboard)

    def _heuristic_fallback(self, blackboard: List[Dict[str, str]]) -> SupervisorDecision:
        """Deterministic state-machine fallback if API is unreachable."""
        senders = [b["sender"] for b in blackboard]
        contents = " ".join([b["content"] for b in blackboard])

        if "NETWORK_SPECIALIST" not in senders:
            return SupervisorDecision(
                reasoning="Verify whether third-party payment gateway or network ingress is failing.",
                next_worker="NETWORK_SPECIALIST",
                instruction="Check external payment gateway latency and ingress traffic for 504 errors."
            )
        elif "DB_SPECIALIST" not in senders:
            return SupervisorDecision(
                reasoning="Network is healthy. Suspect internal database bottleneck or connection exhaustion.",
                next_worker="DB_SPECIALIST",
                instruction="Inspect database connection pool metrics and active slow query locks."
            )
        elif "TX_99482" in contents and "forcefully terminated" not in contents:
            return SupervisorDecision(
                reasoning="Found runaway transaction TX_99482 locking table. Must terminate it immediately.",
                next_worker="DB_SPECIALIST",
                instruction="Terminate blocking transaction TX_99482 to release exclusive row locks."
            )
        elif "INFRA_SPECIALIST" not in senders or "Rolling restart triggered" not in contents:
            return SupervisorDecision(
                reasoning="Locks are cleared, but payment-service pods are hung. Need rolling restart.",
                next_worker="INFRA_SPECIALIST",
                instruction="Perform rolling restart on payment-service to restore healthy pod replicas."
            )
        else:
            return SupervisorDecision(
                reasoning="All root causes remediated and payment service verified healthy.",
                next_worker="FINISH",
                instruction="Incident successfully resolved."
            )


# =====================================================================
# 6. Multi-Agent Orchestration Engine (Supervisor-Worker Graph)
# =====================================================================

class MultiAgentIncidentOrchestrator:
    """Runs the cyclical Supervisor-Worker loop:
    
    Supervisor ──► Chooses Worker ──► Worker Executes ──► Adds to Blackboard
         ▲                                                       │
         └───────────────────────────────────────────────────────┘
                                   │
                         (If Worker == 'FINISH')
                                   ▼
                            Final Postmortem
    """

    def __init__(self):
        self.supervisor = IncidentSupervisorAgent()
        self.workers = {
            "DB_SPECIALIST": DatabaseSpecialistAgent(),
            "NETWORK_SPECIALIST": NetworkSpecialistAgent(),
            "INFRA_SPECIALIST": InfraSpecialistAgent(),
        }

    def run(self, incident: Dict[str, Any], max_turns: int = 6) -> Dict[str, Any]:
        blackboard: List[Dict[str, str]] = []
        turn = 0

        print("\n" + "=" * 75)
        print(f"[!] SRE INCIDENT COMMAND ACTIVATED: {incident['title']}")
        print(f"    Service: {incident['service']} | Severity: {incident['severity']}")
        print("=" * 75)

        while turn < max_turns:
            turn += 1
            print(f"\n" + "-" * 75)
            print(f">>> [Turn {turn}] Incident Commander Evaluating Situation...")
            print("-" * 75)

            # 1. Supervisor evaluates blackboard and decides next step
            decision = self.supervisor.decide(incident, blackboard)
            print(f"[*] [Supervisor Reasoning]:\n    {decision.reasoning}")
            print(f"[>] [Supervisor Decision ]: Dispatching --> '{decision.next_worker}'")

            # 2. Check if incident resolution is complete
            if decision.next_worker == "FINISH":
                print("\n[OK] [Supervisor]: All systems recovered and verified. Ending incident triage.")
                break

            # 3. Look up and invoke the selected worker agent
            worker = self.workers.get(decision.next_worker)
            if not worker:
                raise ValueError(f"Unknown worker: {decision.next_worker}")

            # 4. Worker executes within its specialized sandbox
            findings = worker.execute(decision.instruction)

            # 5. Append findings to shared blackboard
            blackboard.append({
                "sender": worker.NAME,
                "instruction": decision.instruction,
                "content": findings
            })

        # Generate Postmortem Summary
        postmortem = self._generate_postmortem(incident, blackboard)
        return {
            "turns_taken": turn,
            "blackboard": blackboard,
            "postmortem": postmortem
        }

    def _generate_postmortem(self, incident: Dict[str, Any], blackboard: List[Dict[str, str]]) -> str:
        timeline = "\n".join([f"- Step {i+1} [{item['sender']}]: {item['instruction']}\n  Result: {item['content'][:120]}..." for i, item in enumerate(blackboard)])
        return f"""
===========================================================================
                      SRE INCIDENT RESOLUTION POSTMORTEM
===========================================================================
Incident      : {incident['title']} ({incident['severity']})
Service       : {incident['service']}
Investigation Timeline:
{timeline}
Status        : RESOLVED (Full Service Restored)
===========================================================================
"""


# =====================================================================
# 7. Demonstration Run
# =====================================================================
if __name__ == "__main__":
    incident_ticket = {
        "title": "Severe Payment Gateway 504 Timeouts & Checkout Drops",
        "description": "Customer checkout failure rate jumped to 78%. Backend payment-service returning HTTP 504. P99 latency reached 8,200ms.",
        "service": "payment-service",
        "severity": "SEV-1 (CRITICAL)"
    }

    orchestrator = MultiAgentIncidentOrchestrator()
    result = orchestrator.run(incident_ticket)

    print(result["postmortem"])
