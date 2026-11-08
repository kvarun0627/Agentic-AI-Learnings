# Project 01: LLM Basics & Structured Outputs

## What is this?
Before building agents that take actions, we must understand the core engine: the Large Language Model (LLM).

## The Backend Engineer's Mental Model
1. **Stateless RPC**: An LLM is just a function: `f(Prompt, Config) -> String`. It has NO internal state, NO memory between calls, and NO database.
2. **Tokens**: Models do not see characters or words; they see "tokens" (chunks of ~4 characters). Pricing and context limits are strictly measured in tokens.
3. **Roles**:
   - `system` (or system instruction): The baseline persona and immutable rules.
   - `user`: The requester or external caller.
   - `model` (or assistant): The model's generated response.
4. **Structured Outputs**: Instead of asking for raw text and writing brittle regex, modern APIs allow enforcing strict schemas (like Jackson/Pydantic DTOs).

## Files in this Lab
- `01_hello_llm.py`: Basic stateless prompt & response inspection (tokens, latency, roles).
- `02_structured_output.py`: Returning strictly typed Pydantic models (DTOs) from the LLM.
