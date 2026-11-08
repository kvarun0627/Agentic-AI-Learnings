import os
from typing import List, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "gemini-3.5-flash-lite"

# =====================================================================
# For Spring Boot developers:
# Think of Pydantic models as Java DTO classes with Jackson & Bean Validation annotations:
#
# public record ActionPlan(
#     @NotBlank String intent,
#     @Min(1) @Max(5) int urgencyLevel,
#     List<String> requiredActions,
#     @Nullable String followUpDepartment
# ) {}
# =====================================================================

# class ActionPlan(BaseModel):
#     intent: str = Field(description="The primary intent of the incoming user request")
#     urgency_level: int = Field(description="Urgency from 1 (lowest) to 5 (critical)")
#     required_actions: List[str] = Field(description="Step-by-step checklist of backend actions to take")
#     follow_up_department: Optional[str] = Field(description="Target department (e.g., Billing, DevOps, Support) or null")

# def parse_user_ticket(ticket_text: str):
#     print(f"\nIncoming Unstructured Ticket:\n\"{ticket_text}\"\n")

#     # We tell Gemini to enforce the response schema using our Pydantic class
#     config = types.GenerateContentConfig(
#         response_mime_type="application/json",
#         response_schema=ActionPlan,
#         temperature=0.0  # Zero temperature for deterministic classification
#     )

#     response = client.models.generate_content(
#         model=MODEL_NAME,
#         contents=f"Analyze this customer ticket and extract the action plan: {ticket_text}",
#         config=config
#     )

#     # Convert the raw JSON string directly into a strongly typed Pydantic object
#     action_plan = ActionPlan.model_validate_json(response.text)

#     print("--- Strongly Typed Output (DTO) ---")
#     print(f"Intent:           {action_plan.intent}")
#     print(f"Urgency:          {action_plan.urgency_level}/5")
#     print(f"Department:       {action_plan.follow_up_department}")
#     print("Required Actions:")
#     for i, action in enumerate(action_plan.required_actions, 1):
#         print(f"  {i}. {action}")

#without proper Python Pydantics
# def parse_user_ticket(ticket_text : str):
#     print(f"\nIncoming Unstructured Ticket:\n\"{ticket_text}\"\n")
#     response = client.models.generate_content(
#         model = MODEL_NAME,
#         contents=f"Analyze this customer ticket and extract the action plan: {ticket_text}"
#     )
#     print(response.text)

if __name__ == "__main__":
    # Test 1: Production outage ticket
    parse_user_ticket(
        "URGENT: Our production database on AWS RDS is throwing Connection Pool Exhausted errors. "
        "Users can't checkout! Fix this ASAP!"
    )

    # Test 2: Standard invoice question
    parse_user_ticket(
        "Hello, I was charged twice for subscription renewal last Tuesday. Can someone review invoice #4819?"
    )
