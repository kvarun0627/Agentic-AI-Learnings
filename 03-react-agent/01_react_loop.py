import os
import json
import time
from typing import Callable, Dict, Any, List
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.5-flash-lite"

# =====================================================================
# Simulated Production Backend Services (DevOps / Microservices DB)
# =====================================================================

SERVICES_DB = {
    "auth-service": {
        "status": "DEGRADED",
        "pods": {
            "auth-srv-101": {"cpu_percent": 12, "memory_mb": 420, "restarts": 0, "status": "Running"},
            "auth-srv-102": {"cpu_percent": 99, "memory_mb": 2048, "restarts": 14, "status": "CrashLoopBackOff"},
        }
    },
    "payment-service": {
        "status": "HEALTHY",
        "pods": {
            "pay-srv-201": {"cpu_percent": 24, "memory_mb": 512, "restarts": 0, "status": "Running"},
            "pay-srv-202": {"cpu_percent": 18, "memory_mb": 490, "restarts": 0, "status": "Running"},
        }
    }
}

INCIDENT_LOGS = []

# =====================================================================
# Tools Available to the Agent
# =====================================================================

def search_incidents(service_name: str) -> dict:
    """Find active alerts and operational incidents for a microservice.
    
    Args:
        service_name: Name of the microservice (e.g. 'auth-service', 'payment-service')
    """
    svc = SERVICES_DB.get(service_name)
    if not svc:
        return {"error": f"Service '{service_name}' not found. Available services: {list(SERVICES_DB.keys())}"}
    
    if svc["status"] == "HEALTHY":
        return {"service": service_name, "active_alerts": [], "health": "HEALTHY"}
    
    return {
        "service": service_name,
        "health": svc["status"],
        "active_alerts": [
            {"alert_id": "ALT-9081", "type": "HighRestartRate", "severity": "HIGH", "message": "Pod crashloop detected"}
        ]
    }

def get_pod_metrics(service_name: str, pod_name: str) -> dict:
    """Get CPU, memory, and restart metrics for a specific pod.
    
    Args:
        service_name: Name of the service
        pod_name: Name of the pod (e.g., 'auth-srv-101')
    """
    svc = SERVICES_DB.get(service_name)
    if not svc:
        return {"error": f"Service '{service_name}' not found."}
    
    pods = svc["pods"]
    if pod_name not in pods:
        return {
            "error": f"Pod '{pod_name}' does not exist in '{service_name}'. Valid pods are: {list(pods.keys())}"
        }
    
    return {"service": service_name, "pod_name": pod_name, "metrics": pods[pod_name]}

def restart_pod(service_name: str, pod_name: str) -> dict:
    """Restart an unhealthy pod to recover service stability.
    
    Args:
        service_name: Name of the microservice
        pod_name: Name of the specific pod to restart
    """
    svc = SERVICES_DB.get(service_name)
    if not svc:
        return {"error": f"Service '{service_name}' not found."}
    
    if pod_name not in svc["pods"]:
        return {"error": f"Pod '{pod_name}' not found."}
    
    # Simulate restart recovery
    svc["pods"][pod_name]["status"] = "Running"
    svc["pods"][pod_name]["cpu_percent"] = 15
    svc["pods"][pod_name]["memory_mb"] = 410
    svc["status"] = "HEALTHY"
    
    return {
        "status": "SUCCESS",
        "action": "pod_restarted",
        "pod": pod_name,
        "new_status": "Running",
        "message": f"Pod {pod_name} successfully restarted. Metrics normalized."
    }

def send_ops_notification(channel: str, message: str) -> dict:
    """Send an incident summary notification to the DevOps Slack/Teams channel.
    
    Args:
        channel: Ops channel (e.g. '#alerts-backend', '#oncall-eng')
        message: Concise incident summary and action report
    """
    INCIDENT_LOGS.append({"channel": channel, "message": message, "timestamp": time.time()})
    return {"status": "DELIVERED", "channel": channel, "notification_id": f"MSG-{len(INCIDENT_LOGS)}"}

# Tool Registry
TOOL_REGISTRY: Dict[str, Callable] = {
    "search_incidents": search_incidents,
    "get_pod_metrics": get_pod_metrics,
    "restart_pod": restart_pod,
    "send_ops_notification": send_ops_notification
}

# =====================================================================
# The ReAct Agent Loop
# =====================================================================

SYSTEM_INSTRUCTION = """
You are an autonomous Site Reliability & Incident Triage Agent.
Your job is to investigate alerts, diagnose the root cause across pods/services, take corrective remediation actions, and notify the operations team.

GUIDELINES:
1. Always think step-by-step: observe tool outputs before deciding the next action.
2. If a tool call fails or returns an error, examine the error message and self-correct your parameters.
3. When you have resolved the issue and sent necessary notifications, provide a clear, concise final summary.
"""

def run_react_agent(user_prompt: str, max_steps: int = 6) -> str:
    """Executes the autonomous Reason-Act-Observe loop until completion or max_steps."""
    print("\n" + "=" * 75)
    print(f"[GOAL] USER: \"{user_prompt}\"")
    print("=" * 75)
    
    # Configure tools with Automatic Function Calling disabled to retain full control
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=list(TOOL_REGISTRY.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.0
    )
    
    # Initialize message history (the agent's state / scratchpad)
    contents: List[types.Content] = [
        types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
    ]
    
    step = 0
    while step < max_steps:
        step += 1
        print(f"\n--- [STEP {step} / {max_steps}] Agent Reasoning Turn ---")
        
        # 1. Model evaluates state and decides whether to act (call tools) or answer
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config
        )
        
        # Append model's response to history
        contents.append(response.candidates[0].content)
        
        # 2. Check if the model is done (no function calls emitted)
        if not response.function_calls:
            print("\n[GOAL ACHIEVED] Agent decided no more tools are needed.")
            print("\n[FINAL AGENT REPORT]:")
            print(response.text)
            return response.text
        
        # 3. Model requested one or more tool calls (supports Parallel Tool Calling)
        tool_response_parts: List[types.Part] = []
        
        for call in response.function_calls:
            tool_name = call.name
            tool_args = call.args or {}
            
            print(f"  [ACTION] Model invoked: {tool_name}({json.dumps(tool_args)})")
            
            # Execute tool safely with self-healing error capture
            if tool_name not in TOOL_REGISTRY:
                tool_output = {"error": f"Tool '{tool_name}' does not exist in registry."}
            else:
                try:
                    tool_output = TOOL_REGISTRY[tool_name](**tool_args)
                except Exception as e:
                    tool_output = {"error": f"Tool execution failed with exception: {str(e)}"}
            
            print(f"  [OBSERVATION]: {json.dumps(tool_output)}")
            
            # Package result as FunctionResponse
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": tool_output}
                )
            )
        
        # 4. Feed observations back into the agent's scratchpad for the next reasoning turn
        contents.append(types.Content(role="user", parts=tool_response_parts))
    
    warning_msg = f"[LIMIT REACHED] Agent did not complete within {max_steps} steps."
    print(warning_msg)
    return warning_msg


if __name__ == "__main__":
    print("\n=======================================================")
    print(" LAB: Multi-Step Autonomous ReAct Agent Loop")
    print("=======================================================")
    
    # Test Scenario: Multi-step investigation, remediation, and notification
    investigation_query = (
        "We received a high priority alert for 'auth-service'. "
        "Investigate the incident, check metrics for the affected pod, restart the failing pod, "
        "and notify the '#oncall-eng' channel with an incident summary."
    )
    
    run_react_agent(investigation_query)
