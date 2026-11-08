import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1. Load configuration from .env
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

# 2. Instantiate client (think of this as a RestTemplate or WebClient in Spring)
client = genai.Client(api_key=api_key)

# 3. Model selection
# gemini-3.5-flash-lite is optimized for low latency and high reliability
MODEL_NAME = "gemini-3.5-flash-lite"

def test_stateless_call():
    print("--- [1] Simple Prompt & Response ---")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="Explain what an AI Agent is in 2 sentences from a backend engineer's perspective."
    )
    print("Model Output:\n", response.text)
    print(response.candidates)
    # Notice the usage metadata (tokens consumed)
    if response.usage_metadata:
        print("\n[Token Usage]")
        print(f"  Prompt tokens:     {response.usage_metadata.prompt_token_count}")
        print(f"  Candidate tokens:  {response.usage_metadata.candidates_token_count}")
        print(f"  Total tokens:      {response.usage_metadata.total_token_count}")

def test_system_instruction():
    print("\n--- [2] System Instruction (Enforcing Persona) ---")
    # System instructions act as invariant constraints on the model's behavior
    config = types.GenerateContentConfig(
        system_instruction="You are a strict Java Spring Boot Senior Architect. Answer with architectural terminology.",
        temperature=0.2  # 0.0 - 2.0: Lower means more deterministic, higher means more creative
    )
    
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="How should I handle background asynchronous tasks?",
        config=config
    )
    print("Model Output:\n", response.text)

if __name__ == "__main__":
    test_stateless_call()
    test_system_instruction()
