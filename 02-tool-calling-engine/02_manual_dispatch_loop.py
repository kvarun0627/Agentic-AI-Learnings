import os
import json
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
# Banking Service Tools (Simulating real backend operations)
# =====================================================================

ACCOUNTS_DB = {
    "ACC-101": {"owner": "Alice", "balance": 5420.50, "currency": "USD"},
    "ACC-102": {"owner": "Bob", "balance": 150.00, "currency": "USD"},
}

def check_account_balance(account_id: str) -> dict:
    """Fetch the real-time balance and currency for a customer account.
    
    Args:
        account_id: The account number to look up (e.g., 'ACC-101')
    """
    account = ACCOUNTS_DB.get(account_id)
    if not account:
        return {"error": f"Account {account_id} not found."}
    return {"account_id": account_id, "balance": account["balance"], "currency": account["currency"]}

def transfer_funds(from_account: str, to_account: str, amount: float) -> dict:
    """Transfer funds from one account to another. SENSITIVE: Requires authorization.
    
    Args:
        from_account: The source account ID
        to_account: The destination account ID
        amount: The dollar amount to transfer
    """
    source = ACCOUNTS_DB.get(from_account)
    dest = ACCOUNTS_DB.get(to_account)

    if not source:
        return {"success": False, "error": f"Source account {from_account} does not exist."}
    if not dest:
        return {"success": False, "error": f"Destination account {to_account} does not exist."}
    if source["balance"] < amount:
        return {"success": False, "error": f"Insufficient funds. Balance: ${source['balance']}, requested: ${amount}."}

    # Execute atomic transfer
    source["balance"] -= amount
    dest["balance"] += amount
    tx_id = f"TX-{os.urandom(2).hex().upper()}"
    return {
        "success": True,
        "tx_id": tx_id,
        "from": from_account,
        "to": to_account,
        "amount": amount,
        "remaining_balance": source["balance"]
    }

# =====================================================================
# Tool Registry (Like a Spring Bean registry / HandlerMapping)
# Maps string tool names from the LLM to executable Python functions.
# =====================================================================
TOOL_REGISTRY = {
    "check_account_balance": check_account_balance,
    "transfer_funds": transfer_funds,
}

# Critical operations requiring Human-in-the-Loop (HITL) approval
SENSITIVE_TOOLS = {"transfer_funds"}

def security_guard_approval(tool_name: str, args: dict) -> bool:
    """Simulates a security gate / policy check or human confirmation."""
    print(f"\n  [SECURITY GUARD] Intercepted sensitive action: '{tool_name}'")
    print(f"  [SECURITY GUARD] Arguments: {json.dumps(args)}")
    
    # In a real CLI, this would be: input("Approve transfer? [y/N]: ").lower() == 'y'
    # In a web app, this pushes a push notification or OAuth confirmation.
    # Here, we simulate approval if amount <= $10,000
    amount = args.get("amount", 0)
    if amount > 10000:
        print("  [SECURITY GUARD]  REJECTED: Transfer exceeds $10,000 threshold without 2FA.")
        return False
    print("  [SECURITY GUARD]  APPROVED: Passed security verification.")
    return True

def dispatch_user_request(user_prompt: str):
    """Executes the manual 3-step Tool Calling Loop:
    1. Send prompt to model -> get FunctionCall
    2. Intercept & execute the tool in your own code
    3. Send FunctionResponse back to model -> get final answer
    """
    print("\n" + "="*65)
    print(f"USER: \"{user_prompt}\"")
    print("="*65)

    # Disable AFC (Automatic Function Calling) to retain manual control
    config = types.GenerateContentConfig(
        tools=list(TOOL_REGISTRY.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.0
    )

    # -------------------------------------------------------------
    # Step 1: Initial invocation (Model decides if a tool is needed)
    # -------------------------------------------------------------
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=config
    )

    # If no tool is needed, model outputs text directly
    if not response.function_calls:
        print("[LOOP] No tool needed. Direct model response:")
        print(response.text)
        return

    # -------------------------------------------------------------
    # Step 2: Intercept and Execute the Tool Call
    # -------------------------------------------------------------
    for call in response.function_calls:
        tool_name = call.name
        tool_args = call.args

        print(f"\n[STEP 1 - LLM DECISION] Model requested tool call:")
        print(f"  Tool: {tool_name}")
        print(f"  Args: {tool_args}")

        # Check tool registry
        if tool_name not in TOOL_REGISTRY:
            tool_result = {"error": f"Unknown tool '{tool_name}'"}
        else:
            # Check security policy for sensitive tools
            if tool_name in SENSITIVE_TOOLS and not security_guard_approval(tool_name, tool_args):
                tool_result = {"error": "Action rejected: Security threshold / user approval denied."}
            else:
                print(f"[STEP 2 - BACKEND EXECUTION] Executing {tool_name}(...) in local Python...")
                tool_result = TOOL_REGISTRY[tool_name](**tool_args)
                print(f"  Tool Result: {tool_result}")

        # -------------------------------------------------------------
        # Step 3: Send Tool Result Back to Gemini for Final Summary
        # -------------------------------------------------------------
        print(f"\n[STEP 3 - HANDSHAKE] Sending FunctionResponse back to Gemini...")
        
        function_response_part = types.Part.from_function_response(
            name=tool_name,
            response={"result": tool_result}
        )

        # We construct the 3-turn conversation history:
        # 1. User original request
        # 2. Model's tool-call decision
        # 3. Tool execution output
        final_response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]),
                response.candidates[0].content,
                types.Content(role="user", parts=[function_response_part])
            ],
            config=config
        )

        print("\n[FINAL MODEL RESPONSE]:")
        print(final_response.text)

if __name__ == "__main__":
    # Test 1: Read-only query (Safe, executes immediately)
    dispatch_user_request("Can you check the current balance of account ACC-101?")

    # Test 2: Sensitive action within limits (Approved and executed)
    dispatch_user_request("Please transfer $200 from ACC-101 to ACC-102 for groceries.")

    # Test 3: Sensitive action exceeding security limit (Intercepted & blocked)
    dispatch_user_request("Transfer $50,000 from ACC-101 to ACC-102 immediately.")

    # Test 4: General question (No tool needed)
    dispatch_user_request("Why is ACID compliance important in banking databases?")
