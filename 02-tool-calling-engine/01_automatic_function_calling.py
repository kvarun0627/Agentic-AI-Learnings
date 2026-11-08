
import os
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
# For Backend Engineers:
# Think of tools as backend Service methods or RPC endpoints.
# The docstrings and type hints are NOT just documentation—they form the
# OpenAPI / Swagger specification that the LLM reads to decide:
#   1. When to call this function.
#   2. What arguments to extract from the user prompt.
# =====================================================================

# Simulated in-memory database
DATABASE = {
    "ORD-1001": {"status": "DELIVERED", "item": "Ergonomic Mechanical Keyboard", "price": 149.99},
    "ORD-1002": {"status": "PROCESSING", "item": "4K Ultra-wide Monitor", "price": 499.00},
}

def get_order_details(order_id: str) -> dict:
    """Fetch order details and current shipment status by order ID.
    
    Args:
        order_id: The unique identifier of the order (e.g. 'ORD-1001')
    """
    print(f"\n[TOOL CALLED] get_order_details(order_id='{order_id}')")
    order = DATABASE.get(order_id)
    if not order:
        return {"error": f"Order {order_id} not found."}
    return {"order_id": order_id, **order}

def cancel_order(order_id: str, reason: str) -> dict:
    """Cancels a pending or processing customer order.
    
    Args:
        order_id: The unique identifier of the order to cancel
        reason: The reason given by the customer for cancelling
    """
    print(f"\n[TOOL CALLED] cancel_order(order_id='{order_id}', reason='{reason}')")
    order = DATABASE.get(order_id)
    if not order:
        return {"success": False, "message": f"Order {order_id} does not exist."}
    if order["status"] == "DELIVERED":
        return {"success": False, "message": f"Cannot cancel order {order_id}: already DELIVERED. Initiate return instead."}
    
    order["status"] = "CANCELLED"
    return {"success": True, "message": f"Order {order_id} successfully cancelled. Reason: {reason}."}

def main():
    print("=================================================================")
    print("  PHASE 2 - LESSON 1: AUTOMATIC FUNCTION CALLING (AFC)")
    print("=================================================================")

    # Initialize a chat session equipped with our tools
    chat = client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            tools=[get_order_details, cancel_order],
            temperature=0.0  # Zero temperature ensures reliable tool invocation
        )
    )

    # Test 1: Info query (Triggers get_order_details)
    print("\n--- Test 1: Querying Order Status ---")
    query1 = "Can you tell me where order ORD-1001 is and what is inside it?"
    print(f"User: \"{query1}\"")
    response1 = chat.send_message(query1)
    print("Assistant:\n", response1.text)

    # Test 2: Mutation query (Triggers cancel_order on an eligible order)
    print("\n--- Test 2: Cancelling an Eligible Order ---")
    query2 = "I don't need ORD-1002 anymore because I found a cheaper alternative. Please cancel it."
    print(f"User: \"{query2}\"")
    response2 = chat.send_message(query2)
    print("Assistant:\n", response2.text)

    # Test 3: Business rule rejection (Triggers cancel_order on delivered order)
    print("\n--- Test 3: Attempting to Cancel a Delivered Order ---")
    query3 = "Also cancel ORD-1001 for me."
    print(f"User: \"{query3}\"")
    response3 = chat.send_message(query3)
    print("Assistant:\n", response3.text)

    # Test 4: Irrelevant query (No tool needed - answered directly)
    print("\n--- Test 4: Query that does NOT need any tool ---")
    query4 = "What is the difference between TCP and UDP in networking?"
    print(f"User: \"{query4}\"")
    response4 = chat.send_message(query4)
    print("Assistant:\n", response4.text)

if __name__ == "__main__":
    main()
