import os
from typing import List, Dict
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
# Pattern 1: Sliding Window Buffer Memory (FIFO)
# =====================================================================

class SlidingWindowMemory:
    """Retains only the most recent K turns of conversation.
    
    Pros: Extremely cheap, zero additional LLM summarization calls, bounded context.
    Cons: Hard cutoff — forgets critical facts stated early in the conversation.
    """
    def __init__(self, window_size: int = 4):
        self.window_size = window_size
        self.messages: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        # Keep only the last (window_size * 2) messages (user + model pairs)
        max_messages = self.window_size * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def get_messages(self) -> List[Dict[str, str]]:
        return list(self.messages)


# =====================================================================
# Pattern 2: Summary Buffer Memory (Rolling Compression)
# =====================================================================

class SummaryBufferMemory:
    """Maintains a rolling summary of older messages while keeping the most
    recent K turns in raw form.
    
    When message history exceeds max_raw_turns, older messages are compressed
    into an evolving narrative summary by the LLM.
    
    Pros: Long-term retention of critical facts without token explosion.
    Cons: Requires an extra lightweight LLM call to update the summary.
    """
    def __init__(self, client: genai.Client, model: str, max_raw_turns: int = 2):
        self.client = client
        self.model = model
        self.max_raw_turns = max_raw_turns
        self.raw_messages: List[Dict[str, str]] = []
        self.summary: str = ""

    def add_message(self, role: str, content: str):
        self.raw_messages.append({"role": role, "content": content})
        max_messages = self.max_raw_turns * 2
        
        # If we exceed the raw message threshold, compress the oldest turn
        if len(self.raw_messages) > max_messages:
            # Take the oldest pair (user + model) to compress into summary
            oldest_pair = self.raw_messages[:2]
            self.raw_messages = self.raw_messages[2:]
            self._update_summary(oldest_pair)

    def _update_summary(self, new_messages: List[Dict[str, str]]):
        """Asks the model to compress older interactions into the ongoing summary."""
        old_dialogue = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in new_messages)
        
        prompt = f"""You are a conversation summarizer for an AI agent.
Current ongoing summary:
\"\"\"{self.summary}\"\"\"

New dialogue lines to integrate:
\"\"\"{old_dialogue}\"\"\"

Provide an updated, concise summary that preserves all key facts, configurations, IPs, identifiers, and decisions.
Summary:"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0)
        )
        self.summary = response.text.strip()

    def get_prompt_context(self) -> str:
        """Returns the synthesized memory block to inject into the LLM system prompt."""
        context = ""
        if self.summary:
            context += f"### Summary of Earlier Conversation:\n{self.summary}\n\n"
        return context

    def get_messages(self) -> List[Dict[str, str]]:
        return list(self.raw_messages)


# =====================================================================
# Simulation & Comparison Lab
# =====================================================================

def simulate_conversation():
    print("=" * 75)
    print(" LAB: Short-Term Memory & Context Management")
    print("=" * 75)

    # Simulated multi-turn dialogue with crucial early facts
    dialogue_script = [
        ("user", "Hello! I am configuring our payment gateway. The server IP is 10.0.4.55 and the port is 8443."),
        ("model", "Got it. I've noted that the payment gateway is at 10.0.4.55:8443."),
        ("user", "We also use TLS 1.3 with an internal certificate authority."),
        ("model", "Understood. TLS 1.3 is configured with your internal CA."),
        ("user", "Please check if Redis cache is needed for session storage."),
        ("model", "Yes, Redis cache is recommended for distributed session storage."),
        ("user", "Can we enable rate limiting at 500 requests per minute?"),
        ("model", "Yes, rate limiting can be configured in your API gateway for 500 req/min.")
    ]

    print("\n[Step 1] Feeding 4 turns of dialogue into both memory systems...")
    
    # 1. Initialize both memory systems
    # Sliding window keeps only the last 2 turns (4 messages)
    sliding_mem = SlidingWindowMemory(window_size=2)
    # Summary buffer keeps last 1 turn in raw, summarizes older turns
    summary_mem = SummaryBufferMemory(client=client, model=MODEL_NAME, max_raw_turns=1)

    for role, text in dialogue_script:
        sliding_mem.add_message(role, text)
        summary_mem.add_message(role, text)

    # 2. Inspect internal states
    print("\n--- Sliding Window Memory State ---")
    print(f"Retained Message Count: {len(sliding_mem.get_messages())}")
    for idx, msg in enumerate(sliding_mem.get_messages(), 1):
        print(f"  {idx}. [{msg['role']}]: {msg['content'][:60]}...")

    print("\n--- Summary Buffer Memory State ---")
    print(f"Compressed Rolling Summary:\n  \"{summary_mem.summary}\"")
    print(f"Active Raw Messages: {len(summary_mem.get_messages())}")

    # 3. Test Retrieval of Early Facts
    test_question = "What is the server IP and port for the payment gateway?"
    print(f"\n[Step 2] Testing Recall: \"{test_question}\"\n")

    # A. Test Sliding Window
    print(">>> Testing Sliding Window Agent:")
    sliding_contents = [
        types.Content(role=m["role"], parts=[types.Part.from_text(text=m["content"])])
        for m in sliding_mem.get_messages()
    ]
    sliding_contents.append(types.Content(role="user", parts=[types.Part.from_text(text=test_question)]))
    
    sliding_resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=sliding_contents,
        config=types.GenerateContentConfig(temperature=0.0)
    )
    print(f"Response: {sliding_resp.text.strip()}\n")

    # B. Test Summary Buffer
    print(">>> Testing Summary Buffer Agent:")
    summary_sys_instruction = (
        "You are a helpful assistant.\n" + summary_mem.get_prompt_context()
    )
    summary_contents = [
        types.Content(role=m["role"], parts=[types.Part.from_text(text=m["content"])])
        for m in summary_mem.get_messages()
    ]
    summary_contents.append(types.Content(role="user", parts=[types.Part.from_text(text=test_question)]))
    
    summary_resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=summary_contents,
        config=types.GenerateContentConfig(
            system_instruction=summary_sys_instruction,
            temperature=0.0
        )
    )
    print(f"Response: {summary_resp.text.strip()}\n")

    print("=" * 75)
    print(" LAB INSIGHT:")
    print(" - Sliding Window FORGOT the IP/port because it was pushed out of the buffer.")
    print(" - Summary Buffer RETAINED the IP/port because the LLM compressed it into the ongoing summary.")
    print("=" * 75)


if __name__ == "__main__":
    simulate_conversation()
