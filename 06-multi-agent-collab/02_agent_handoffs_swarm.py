import os
import sys
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

# Ensure UTF-8 output across Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from dotenv import load_dotenv
from google import genai
from google.genai import types

# =====================================================================
# 1. Environment & Setup
# =====================================================================
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.5-flash-lite"


# =====================================================================
# 2. Domain Data & Backend Microservices
# =====================================================================

MOCK_ACCOUNTS_DB = {
    "CUST-8831": {
        "customer_id": "CUST-8831",
        "name": "Sarah Connor",
        "tier": "VIP_PLATINUM",
        "email": "sconnor@cyberdyne.org",
        "phone": "+1-312-555-0199",
        "billing_address": "Chicago, IL, United States",
        "active_card_last4": "4092",
        "card_status": "ACTIVE"
    }
}

MOCK_TRANSACTIONS_DB = {
    "CUST-8831": [
        {
            "tx_id": "TX_US_1001",
            "merchant": "Whole Foods Chicago",
            "amount_usd": 64.20,
            "location": "Chicago, IL, US",
            "status": "SETTLED",
            "timestamp": "2026-10-27T14:20:00Z"
        },
        {
            "tx_id": "TX_UKR_8819",
            "merchant": "Kyiv Luxury Watch Outlet",
            "amount_usd": 1250.00,
            "location": "Kyiv, Ukraine",
            "status": "PENDING",
            "timestamp": "2026-10-28T02:15:00Z"
        }
    ]
}

# --- Triage Microservice Tools ---
def lookup_customer_account(customer_id: str) -> dict:
    """Retrieves customer identity, membership tier, active card, and account status.
    
    Args:
        customer_id: The unique customer identifier (e.g., 'CUST-8831').
    """
    account = MOCK_ACCOUNTS_DB.get(customer_id)
    if not account:
        return {"status": "ERROR", "message": f"Customer ID '{customer_id}' not found."}
    return {"status": "SUCCESS", "account": account}


# --- Billing Microservice Tools ---
def inspect_recent_transactions(customer_id: str) -> dict:
    """Lists recent transactions for an account including location, amount, and settlement status.
    
    Args:
        customer_id: The customer account ID to inspect.
    """
    txs = MOCK_TRANSACTIONS_DB.get(customer_id, [])
    return {"status": "SUCCESS", "customer_id": customer_id, "transaction_count": len(txs), "transactions": txs}

def reverse_unauthorized_transaction(tx_id: str, reason: str) -> dict:
    """Halts and reverses a pending unauthorized charge, issuing an immediate ledger credit.
    
    Args:
        tx_id: The transaction ID to cancel and refund (e.g., 'TX_UKR_8819').
        reason: Justification for reversal (e.g., 'Confirmed card-not-present fraud').
    """
    return {
        "status": "REVERSED",
        "tx_id": tx_id,
        "amount_refunded_usd": 1250.00,
        "reversal_reason": reason,
        "ledger_confirmation": f"CREDIT-REV-{tx_id}-OK"
    }


# --- Fraud & Security Microservice Tools ---
def freeze_compromised_card(card_last4: str, reason: str) -> dict:
    """Immediately locks and permanently deactivates a payment card to prevent further charges.
    
    Args:
        card_last4: The last 4 digits of the card to freeze (e.g., '4092').
        reason: Explanation of the security breach triggering the lock.
    """
    if "CUST-8831" in MOCK_ACCOUNTS_DB:
        MOCK_ACCOUNTS_DB["CUST-8831"]["card_status"] = "FROZEN"
    return {
        "status": "SUCCESS",
        "action": "CARD_FROZEN",
        "card_last4": card_last4,
        "reason": reason,
        "incident_ticket_id": "SEC-TICKET-99214"
    }

def issue_replacement_card(customer_id: str, delivery_speed: str = "EXPEDITED") -> dict:
    """Provisions a brand new digital payment card and orders an expedited physical replacement.
    
    Args:
        customer_id: Customer ID receiving the replacement card.
        delivery_speed: 'STANDARD' or 'EXPEDITED'.
    """
    return {
        "status": "SUCCESS",
        "customer_id": customer_id,
        "new_card_last4": "9144",
        "digital_wallet_push_ready": True,
        "physical_dispatch": f"DISPATCHED_{delivery_speed}",
        "estimated_arrival": "24 hours via courier"
    }


# =====================================================================
# 3. Handoff Contract & Peer Agent Architecture
# =====================================================================

@dataclass
class HandoffArtifact:
    """Data transfer object created when an agent transfers control to a peer."""
    from_agent: str
    target_agent: str
    reason: str
    handover_notes: str


@dataclass
class PeerAgent:
    """Autonomous peer agent in a decentralized collaborative swarm."""
    name: str
    system_instruction: str
    tools: Dict[str, Callable]
    handoff_targets: List[str] = field(default_factory=list)


# =====================================================================
# 4. Agent Personas & Factory
# =====================================================================

def build_support_swarm() -> Dict[str, PeerAgent]:
    """Configures the specialized peer agents and their handoff network."""

    triage_agent = PeerAgent(
        name="TRIAGE_AGENT",
        system_instruction="""You are the Frontline Triage Specialist for Apex Digital Banking.
Your exact mission:
1. Verify customer identity using 'lookup_customer_account'.
2. If the customer reports unrecognized, stolen, or fraudulent transactions, you MUST hand off immediately to 'BILLING_AGENT' using 'transfer_to_billing_agent'.
3. Do NOT attempt to investigate billing details or issue refunds yourself. Handoff is required.
Always call tools to perform actions.""",
        tools={
            "lookup_customer_account": lookup_customer_account
        },
        handoff_targets=["BILLING_AGENT"]
    )

    billing_agent = PeerAgent(
        name="BILLING_AGENT",
        system_instruction="""You are the Senior Billing & Disputed Charges Specialist.
Your exact mission:
1. Inspect the customer's recent transactions using 'inspect_recent_transactions'.
2. When you detect the fraudulent pending transaction, reverse it using 'reverse_unauthorized_transaction'.
3. CRITICAL: Because this charge indicates physical/digital card compromise (e.g. overseas fraudulent charge), you MUST hand off to 'FRAUD_AGENT' using 'transfer_to_fraud_agent' so they can freeze the compromised card and issue a replacement.
Do NOT attempt to freeze cards or issue new cards yourself. Handoff is required after refunding.""",
        tools={
            "inspect_recent_transactions": inspect_recent_transactions,
            "reverse_unauthorized_transaction": reverse_unauthorized_transaction
        },
        handoff_targets=["FRAUD_AGENT"]
    )

    fraud_agent = PeerAgent(
        name="FRAUD_AGENT",
        system_instruction="""You are the Fraud Mitigation & Card Security Specialist.
Your exact mission:
1. Review the handover notes and security incident details.
2. Freeze the compromised card ending in 4092 using 'freeze_compromised_card'.
3. Issue a new replacement card for the customer using 'issue_replacement_card'.
4. After completing these actions, write a complete, reassuring final message directly to the customer confirming:
   - The unauthorized $1,250 charge in Kyiv was reversed and refunded.
   - The compromised card (*4092) was frozen.
   - A new card (*9144) was issued to their digital wallet and physical card dispatched.
You have no further agents to hand off to; you deliver the final customer resolution.""",
        tools={
            "freeze_compromised_card": freeze_compromised_card,
            "issue_replacement_card": issue_replacement_card
        },
        handoff_targets=[]  # Terminal agent: speaks to user
    )

    return {
        "TRIAGE_AGENT": triage_agent,
        "BILLING_AGENT": billing_agent,
        "FRAUD_AGENT": fraud_agent
    }


# =====================================================================
# 5. Decentralized Swarm Engine (Peer Choreography Runtime)
# =====================================================================

class DecentralizedSwarmEngine:
    """Decentralized Multi-Agent Runtime (The Swarm Pattern).
    
    Key Architectural Characteristics:
    1. Zero Supervisor Bottleneck: There is NO central 'orchestrator' LLM call on every turn.
    2. Dynamic Active Agent: Execution is held exclusively by the active peer agent.
    3. Tool-Driven Handoffs: Handoffs are first-class tools declared in the active agent's toolbelt.
    4. Isolated Context Windows: Each agent only receives relevant domain context and handoff notes,
       preventing cross-agent prompt bloat and tool hallucinations.
    """

    def __init__(self, agents: Dict[str, PeerAgent]):
        self.agents = agents

    def run(self, initial_agent_name: str, customer_ticket: str, max_swarm_hops: int = 5) -> Dict[str, Any]:
        if initial_agent_name not in self.agents:
            raise ValueError(f"Initial agent '{initial_agent_name}' is not registered.")

        current_agent = self.agents[initial_agent_name]
        
        # Shared Context Ledger passed from agent to agent during handoffs
        shared_context_ledger: List[str] = [
            f"[ORIGINAL CUSTOMER TICKET]:\n{customer_ticket}"
        ]

        handoff_audit_trail: List[HandoffArtifact] = []
        hop_count = 0
        final_customer_response: Optional[str] = None

        print("\n" + "=" * 80)
        print("[!] DECENTRALIZED MULTI-AGENT SWARM ACTIVATED")
        print(f"    Initial Point of Contact : {current_agent.name}")
        print(f"    Customer Message         : \"{customer_ticket[:90]}...\"")
        print("=" * 80)

        while hop_count < max_swarm_hops:
            hop_count += 1
            print(f"\n" + "-" * 80)
            print(f">>> [Hop {hop_count}] Agent [{current_agent.name}] taking execution ownership")
            print("-" * 80)

            # Execute active agent's autonomous ReAct cycle
            turn_result = self._run_agent_cycle(current_agent, shared_context_ledger)

            # Check if active agent executed a Handoff tool
            if isinstance(turn_result, HandoffArtifact):
                print(f"\n[>>> DYNAMIC PEER HANDOFF TRIGGERED >>>]")
                print(f"    From Agent : {turn_result.from_agent}")
                print(f"    To Agent   : {turn_result.target_agent}")
                print(f"    Reason     : {turn_result.reason}")
                print(f"    Notes      : {turn_result.handover_notes}")

                handoff_audit_trail.append(turn_result)

                # Record the handoff in shared context ledger for the next peer
                shared_context_ledger.append(
                    f"\n[HANDOFF FROM {turn_result.from_agent} TO {turn_result.target_agent}]:\n"
                    f"Reason: {turn_result.reason}\n"
                    f"Handover Notes: {turn_result.handover_notes}"
                )

                # Transfer active agent pointer to the new peer
                current_agent = self.agents[turn_result.target_agent]
                continue

            else:
                # Terminal agent completed all work and produced direct customer response
                final_customer_response = turn_result
                print(f"\n[OK] [{current_agent.name}] Completed all actions and generated customer response.")
                break

        return {
            "total_hops": hop_count,
            "final_agent": current_agent.name,
            "handoff_trail": handoff_audit_trail,
            "final_response": final_customer_response,
            "context_ledger": shared_context_ledger
        }

    def _run_agent_cycle(self, agent: PeerAgent, context_ledger: List[str], max_inner_steps: int = 5) -> Any:
        """Runs the ReAct reason-act-observe loop for the currently active peer agent."""

        # 1. Synthesize handoff tools for this agent's declared peer targets
        handoff_tools: Dict[str, Callable] = {}
        for target in agent.handoff_targets:
            tool_name = f"transfer_to_{target.lower()}"
            
            def make_handoff_func(target_name: str, t_name: str):
                def transfer_func(reason: str, handover_notes: str) -> dict:
                    return {
                        "__is_handoff__": True,
                        "target_agent": target_name,
                        "reason": reason,
                        "handover_notes": handover_notes
                    }
                transfer_func.__name__ = t_name
                transfer_func.__doc__ = f"Transfers full active execution to {target_name}. Use when task falls into {target_name}'s domain."
                return transfer_func

            handoff_tools[tool_name] = make_handoff_func(target, tool_name)

        all_agent_tools = {**agent.tools, **handoff_tools}

        # 2. Configure Gemini with manual function dispatch
        config = types.GenerateContentConfig(
            system_instruction=agent.system_instruction,
            tools=list(all_agent_tools.values()),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.0
        )

        # 3. Prepare initial prompt containing accumulated context ledger
        compiled_context = "\n\n".join(context_ledger)
        contents: List[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=compiled_context)])
        ]

        step = 0
        while step < max_inner_steps:
            step += 1

            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                print(f"   [!] LLM API error ({e}). Using deterministic fallback.")
                return self._deterministic_fallback_cycle(agent, context_ledger)

            # Record model turn in conversation history
            contents.append(response.candidates[0].content)

            # Case A: Model emitted no function calls -> It delivered its text answer
            if not response.function_calls:
                return response.text

            # Case B: Model requested one or more tool calls
            tool_response_parts: List[types.Part] = []

            for call in response.function_calls:
                fn_name = call.name
                fn_args = dict(call.args or {})
                print(f"   [{agent.name}] Invoking Tool: {fn_name}({json.dumps(fn_args)})")

                # Check if this tool is a peer handoff!
                if fn_name in handoff_tools:
                    target_name = fn_name.replace("transfer_to_", "").upper()
                    return HandoffArtifact(
                        from_agent=agent.name,
                        target_agent=target_name,
                        reason=fn_args.get("reason", "Domain escalation"),
                        handover_notes=fn_args.get("handover_notes", "")
                    )

                # Standard domain tool execution
                if fn_name in agent.tools:
                    tool_fn = agent.tools[fn_name]
                    try:
                        tool_result = tool_fn(**fn_args)
                    except Exception as err:
                        tool_result = {"error": f"Tool execution failed: {str(err)}"}

                    print(f"   [{agent.name}] Tool Observation: {json.dumps(tool_result)}")
                    
                    # Log domain tool execution into shared context ledger
                    context_ledger.append(f"[{agent.name} executed {fn_name}]: {json.dumps(tool_result)}")

                    tool_response_parts.append(
                        types.Part.from_function_response(
                            name=fn_name,
                            response={"result": tool_result}
                        )
                    )

            # Send observations back to model for the next step in its inner loop
            contents.append(types.Content(role="user", parts=tool_response_parts))

        return "Agent completed maximum reasoning steps."

    def _deterministic_fallback_cycle(self, agent: PeerAgent, context_ledger: List[str]) -> Any:
        """Deterministic safety-net ensuring predictable lab execution regardless of API variance."""
        if agent.name == "TRIAGE_AGENT":
            acc = lookup_customer_account("CUST-8831")
            print(f"   [{agent.name}] Tool Observation: {json.dumps(acc)}")
            context_ledger.append(f"[{agent.name} executed lookup_customer_account]: {json.dumps(acc)}")
            return HandoffArtifact(
                from_agent="TRIAGE_AGENT",
                target_agent="BILLING_AGENT",
                reason="Customer dispute: unauthorized international charge of $1,250.00.",
                handover_notes="Customer CUST-8831 (Sarah Connor, VIP_PLATINUM). Active card 4092. Needs charge reversal."
            )

        elif agent.name == "BILLING_AGENT":
            txs = inspect_recent_transactions("CUST-8831")
            print(f"   [{agent.name}] Tool Observation: {json.dumps(txs)}")
            context_ledger.append(f"[{agent.name} executed inspect_recent_transactions]: {json.dumps(txs)}")

            rev = reverse_unauthorized_transaction("TX_UKR_8819", "Confirmed fraudulent card-not-present transaction")
            print(f"   [{agent.name}] Tool Observation: {json.dumps(rev)}")
            context_ledger.append(f"[{agent.name} executed reverse_unauthorized_transaction]: {json.dumps(rev)}")

            return HandoffArtifact(
                from_agent="BILLING_AGENT",
                target_agent="FRAUD_AGENT",
                reason="Physical/digital card compromise detected. Immediate freeze and replacement required.",
                handover_notes="Transaction TX_UKR_8819 reversed ($1,250.00). Card ending in 4092 compromised. Requires freeze & re-issue."
            )

        elif agent.name == "FRAUD_AGENT":
            frz = freeze_compromised_card("4092", "Compromised via unauthorized overseas merchant")
            print(f"   [{agent.name}] Tool Observation: {json.dumps(frz)}")
            context_ledger.append(f"[{agent.name} executed freeze_compromised_card]: {json.dumps(frz)}")

            rep = issue_replacement_card("CUST-8831", "EXPEDITED")
            print(f"   [{agent.name}] Tool Observation: {json.dumps(rep)}")
            context_ledger.append(f"[{agent.name} executed issue_replacement_card]: {json.dumps(rep)}")

            return (
                "Dear Ms. Connor,\n\n"
                "We have resolved your emergency request across our specialized teams:\n\n"
                "1. **Disputed Charge Reversed**: Our Billing Department reviewed transaction TX_UKR_8819 "
                "($1,250.00 at Kyiv Luxury Watch Outlet) and immediately reversed the charge. Your account has been credited.\n"
                "2. **Compromised Card Locked**: Your card ending in 4092 has been permanently frozen to prevent further unauthorized access.\n"
                "3. **Replacement Card Issued**: A new digital card ending in 9144 has been provisioned and is ready in your digital wallet. "
                "Your physical titanium card is dispatched via expedited 24-hour courier.\n\n"
                "Your account security is restored. Please let us know if you need any additional assistance!"
            )


# =====================================================================
# 6. Demonstration Run & Comparative Analysis
# =====================================================================

if __name__ == "__main__":
    customer_ticket = (
        "Hello, this is Sarah Connor (Customer ID: CUST-8831). "
        "I just received a mobile alert that someone in Kyiv, Ukraine charged $1,250.00 to my credit card! "
        "I live in Chicago, I have never visited Ukraine, and my physical card is right here in my wallet. "
        "Please reverse this stolen charge immediately, protect my account, and issue me a new card!"
    )

    swarm = build_support_swarm()
    engine = DecentralizedSwarmEngine(swarm)

    result = engine.run(
        initial_agent_name="TRIAGE_AGENT",
        customer_ticket=customer_ticket
    )

    # Output Detailed Architectural Handoff Audit Trail
    print("\n" + "=" * 80)
    print("                    PEER-TO-PEER HANDOFF DELEGATION AUDIT")
    print("=" * 80)
    print("Delegation Topology:")
    print("  [Customer] ──► [TRIAGE_AGENT] ──handoff──► [BILLING_AGENT] ──handoff──► [FRAUD_AGENT] ──► [Customer]\n")

    for i, step in enumerate(result["handoff_trail"], 1):
        print(f"  Step {i}: [{step.from_agent}] ──────► [{step.target_agent}]")
        print(f"          Reason : {step.reason}")
        print(f"          Notes  : {step.handover_notes}")
        print("  " + "-" * 76)

    print(f"\nFinal Responding Specialist: [{result['final_agent']}]")
    print(f"Total Peer Transitions     : {len(result['handoff_trail'])}")
    print(f"Total Swarm Hops Taken     : {result['total_hops']}")

    print("\n" + "=" * 80)
    print("                      FINAL CUSTOMER RESOLUTION")
    print("=" * 80)
    print(result["final_response"])
    print("=" * 80)
