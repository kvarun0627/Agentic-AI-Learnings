import os
import sys
import json
import asyncio
import argparse
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

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# =====================================================================
# 1. Environment & Setup
# =====================================================================
# Load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in .env file!")

gemini_client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.5-flash-lite"
FALLBACK_MODEL = "gemini-3.8-flash"

SERVER_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "01_mcp_server.py")

async def generate_content_resilient(contents: List[types.Content], config: types.GenerateContentConfig, max_retries: int = 3) -> types.GenerateContentResponse:
    """Invokes Gemini with exponential backoff on transient 503/429 spikes, with fallback model support."""
    models = [MODEL_NAME, FALLBACK_MODEL]
    last_exc = None
    
    for model in models:
        for attempt in range(1, max_retries + 1):
            try:
                return await gemini_client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
            except Exception as exc:
                last_exc = exc
                err_msg = str(exc)
                if ("503" in err_msg or "429" in err_msg) and attempt < max_retries:
                    backoff = 2 ** attempt
                    print(f"    [!] API high demand ({model}). Retrying in {backoff}s (attempt {attempt}/{max_retries})...")
                    await asyncio.sleep(backoff)
                    continue
                # If we've exhausted retries for this model, try fallback model
                break
    raise last_exc


# =====================================================================
# 2. MCP Client Bridge & Schema Adapter
# =====================================================================
class MCPClientBridge:
    """Manages the lifecycle of an MCP subprocess server connection over stdio.
    
    Handles:
    1. Spawning the MCP server subprocess via JSON-RPC 2.0 stdio pipes.
    2. Protocol handshake & capability negotiation.
    3. Translating MCP Tool JSON Schemas into Gemini Function Declarations.
    4. Querying MCP Resources (e.g. database schemas, live telemetry).
    5. Retrieving MCP Server Prompts (reusable incident diagnosis templates).
    6. Executing remote tool dispatches over JSON-RPC.
    """

    def __init__(self, server_path: str):
        self.server_path = server_path
        self.session: Optional[ClientSession] = None
        self._stdio_ctx = None
        self.gemini_tools: List[types.Tool] = []
        self.discovered_tool_names: List[str] = []

    async def connect(self):
        """Spawns the MCP server and executes the protocol handshake."""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_path, "--stdio"],
            env=os.environ.copy()
        )
        
        self._stdio_ctx = stdio_client(server_params)
        read_stream, write_stream = await self._stdio_ctx.__aenter__()
        
        self.session = ClientSession(read_stream, write_stream)
        await self.session.__aenter__()
        await self.session.initialize()

    async def disconnect(self):
        """Gracefully terminates the MCP session and sub-process."""
        if self.session:
            try:
                await self.session.__aexit__(None, None, None)
            except Exception:
                pass
        if self._stdio_ctx:
            try:
                await self._stdio_ctx.__aexit__(None, None, None)
            except Exception:
                pass

    async def discover_tools(self) -> List[types.Tool]:
        """Discovers all MCP tools and converts their JSON Schemas to Gemini FunctionDeclarations."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected.")

        tools_result = await self.session.list_tools()
        function_declarations: List[types.FunctionDeclaration] = []
        self.discovered_tool_names = []

        for mcp_tool in tools_result.tools:
            self.discovered_tool_names.append(mcp_tool.name)
            func_decl = types.FunctionDeclaration(
                name=mcp_tool.name,
                description=mcp_tool.description or "MCP remote tool",
                parameters=mcp_tool.input_schema
            )
            function_declarations.append(func_decl)

        self.gemini_tools = [types.Tool(function_declarations=function_declarations)]
        return self.gemini_tools

    async def fetch_resource(self, uri: str) -> str:
        """Reads read-only contextual data from an MCP resource URI."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected.")
        res = await self.session.read_resource(uri)
        chunks = [c.text for c in res.contents if hasattr(c, "text")]
        return "\n".join(chunks)

    async def fetch_prompt(self, name: str, arguments: Dict[str, str]) -> str:
        """Retrieves a standardized workflow prompt from the MCP server."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected.")
        prompt_data = await self.session.get_prompt(name, arguments=arguments)
        messages_text = []
        for msg in prompt_data.messages:
            if hasattr(msg.content, "text"):
                messages_text.append(msg.content.text)
        return "\n\n".join(messages_text)

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Dispatches a tool call request over JSON-RPC 2.0 to the MCP server."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected.")
        result = await self.session.call_tool(name, arguments)
        text_parts = [c.text for c in result.content if hasattr(c, "text")]
        return "\n".join(text_parts)


# =====================================================================
# 3. Autonomous MCP ReAct Agent
# =====================================================================
class AutonomousMCPAgent:
    """Autonomous ReAct agent powered by Gemini and backed by an MCP Server."""

    def __init__(self, bridge: MCPClientBridge, system_context: str = ""):
        self.bridge = bridge
        self.system_context = system_context

    async def run(self, user_prompt: str, max_turns: int = 8) -> str:
        """Executes the multi-turn Reason-Act-Observe loop using MCP tools."""
        print("\n" + "=" * 80)
        print(f"[*] MCP AGENT GOAL: \"{user_prompt}\"")
        print("=" * 80)

        # Base instructions grounded by MCP protocol
        system_instruction = f"""You are an autonomous Enterprise Banking and SRE Operations Agent.
You interact with the backend infrastructure EXCLUSIVELY via standard Model Context Protocol (MCP) tools.

Operational Grounding & Resources:
{self.system_context}

Protocol Guidelines:
1. Always analyze database queries against the banking schema before execution.
2. Read-only queries must use 'query_database_readonly'.
3. Fund transfers must use 'transfer_funds_atomic' and include an idempotency key to prevent double charge.
4. Container restarts must specify valid targets: 'payment-gateway', 'auth-service', 'ledger-db', or 'notification-worker'.
5. Reason through each step methodically: inspect observations before deciding subsequent actions.
6. When your task is completed, formulate a comprehensive, executive-ready summary.
"""

        # GenerateContent configuration: disable automatic function calling to retain manual control
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=self.bridge.gemini_tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.0
        )

        contents: List[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
        ]

        turn = 0
        while turn < max_turns:
            turn += 1
            print(f"\n--- [TURN {turn}/{max_turns}] Agent Reasoning ---")

            response = await generate_content_resilient(
                contents=contents,
                config=config
            )

            # Append assistant response candidate to history
            contents.append(response.candidates[0].content)

            # Check if LLM is satisfied and has produced a final answer
            if not response.function_calls:
                print("\n[+] Agent Goal Completed (No further tool dispatches required).")
                print("\n" + "=" * 80)
                print("                     FINAL AGENT REPORT")
                print("=" * 80)
                print(response.text)
                print("=" * 80)
                return response.text

            # Execute Model-Directed Tool Calls over MCP
            tool_response_parts: List[types.Part] = []

            for call in response.function_calls:
                tool_name = call.name
                tool_args = call.args or {}

                print(f"\n  [THOUGHT & ACTION] Gemini decided to invoke MCP Tool:")
                print(f"    -> Tool Name : {tool_name}")
                print(f"    -> Arguments : {json.dumps(tool_args)}")

                try:
                    # Dispatch to MCP Server via stdio JSON-RPC 2.0
                    raw_result = await self.bridge.call_tool(tool_name, tool_args)
                    print(f"  [OBSERVATION FROM MCP SERVER]:")
                    preview = raw_result[:250] + ("..." if len(raw_result) > 250 else "")
                    print(f"    {preview}")
                    
                    tool_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"result": raw_result}
                        )
                    )
                except Exception as exc:
                    error_msg = f"MCP execution error: {str(exc)}"
                    print(f"  [MCP ERROR]: {error_msg}")
                    tool_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"error": error_msg}
                        )
                    )

            # Feed observation back as user/tool response into conversation history
            contents.append(types.Content(role="user", parts=tool_response_parts))

        limit_msg = f"Task aborted: Agent exceeded maximum allocated turns ({max_turns})."
        print(f"\n[-] {limit_msg}")
        return limit_msg


# =====================================================================
# 4. Pre-Packaged Demo Scenarios
# =====================================================================
async def run_scenario_1_sql_investigation(bridge: MCPClientBridge, schema_resource: str):
    """Scenario 1: Read-only autonomous SQL inspection and balance lookup."""
    agent = AutonomousMCPAgent(bridge, system_context=schema_resource)
    prompt = (
        "Run a read-only SQL query to list all active accounts in the bank. "
        "Summarize each customer's account ID, name, tier, and balance."
    )
    await agent.run(prompt)


async def run_scenario_2_atomic_transfer(bridge: MCPClientBridge, schema_resource: str):
    """Scenario 2: Multi-step ACID atomic transfer and ledger audit verification."""
    agent = AutonomousMCPAgent(bridge, system_context=schema_resource)
    prompt = (
        "Transfer $75.00 from Alice Cooper (account 'ACC-1001') to Bob Vance (account 'ACC-1002') "
        "using idempotency key 'TX-AUDIT-9901'. Then query the accounts table and the audit ledger "
        "to verify both balances and the recorded transaction."
    )
    await agent.run(prompt)


async def run_scenario_3_incident_triage(bridge: MCPClientBridge, schema_resource: str):
    """Scenario 3: Resource-grounded incident triage using MCP prompt template & microservice restart."""
    # 1. Fetch server prompt template
    triage_prompt = await bridge.fetch_prompt(
        name="diagnose_payment_incident",
        arguments={
            "customer_id": "ACC-1003",
            "issue_description": "Customer unable to transact; payment gateway reporting errors."
        }
    )
    
    # 2. Fetch live telemetry resource
    telemetry = await bridge.fetch_resource("system://telemetry/live")
    system_context = f"{schema_resource}\n\nLive System Telemetry:\n{telemetry}"

    agent = AutonomousMCPAgent(bridge, system_context=system_context)
    await agent.run(triage_prompt)


# =====================================================================
# 5. CLI Entrypoint & Interactive Dispatcher
# =====================================================================
async def main():
    parser = argparse.ArgumentParser(description="Autonomous MCP Client Agent (Gemini + Model Context Protocol)")
    parser.add_argument(
        "--scenario",
        type=int,
        choices=[1, 2, 3],
        help="Run a specific demo scenario: 1 (SQL Investigation), 2 (Atomic Transfer), 3 (Incident Triage)"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="Custom user instruction for the autonomous MCP agent"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start an interactive prompt loop with the live MCP Agent"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("   AUTONOMOUS MCP CLIENT AGENT (GEMINI 3.5 FLASH + PROTOCOL WIRE)")
    print(f"   Connecting to Server: {SERVER_SCRIPT_PATH}")
    print("=" * 80)

    # Initialize MCP Bridge and Handshake
    bridge = MCPClientBridge(SERVER_SCRIPT_PATH)
    await bridge.connect()

    try:
        # 1. Discover MCP Server Capabilities
        tools = await bridge.discover_tools()
        print(f"\n[+] MCP Handshake Successful!")
        print(f"[+] Discovered {len(bridge.discovered_tool_names)} Remote Tools from MCP Server:")
        for name in bridge.discovered_tool_names:
            print(f"    * {name}")

        # 2. Ground agent with MCP Resource (Banking Schema)
        schema_resource = await bridge.fetch_resource("banking://database/schema")
        print(f"[+] Retrieved Context Resource: 'banking://database/schema' ({len(schema_resource)} bytes)")

        # Scenario Dispatch
        if args.scenario == 1:
            await run_scenario_1_sql_investigation(bridge, schema_resource)
        elif args.scenario == 2:
            await run_scenario_2_atomic_transfer(bridge, schema_resource)
        elif args.scenario == 3:
            await run_scenario_3_incident_triage(bridge, schema_resource)
        elif args.prompt:
            agent = AutonomousMCPAgent(bridge, system_context=schema_resource)
            await agent.run(args.prompt)
        elif args.interactive:
            print("\n" + "=" * 80)
            print(" ENTERING INTERACTIVE MCP AGENT SHELL (Type 'exit' or 'quit' to end)")
            print("=" * 80)
            agent = AutonomousMCPAgent(bridge, system_context=schema_resource)
            while True:
                try:
                    user_input = input("\nAgent Task > ").strip()
                    if not user_input:
                        continue
                    if user_input.lower() in ("exit", "quit"):
                        print("[*] Exiting interactive shell.")
                        break
                    await agent.run(user_input)
                except (KeyboardInterrupt, EOFError):
                    break
        else:
            # Default run: Execute all three scenarios sequentially to demonstrate full MCP lifecycle
            print("\n[!] No specific scenario flag provided. Executing standard demonstration suite...")
            print("\n>>> Scenario 1: Autonomous SQL Investigation & Read-Only Auditing")
            await run_scenario_1_sql_investigation(bridge, schema_resource)

            print("\n>>> Scenario 2: Autonomous ACID Atomic Transfer & Idempotency")
            await run_scenario_2_atomic_transfer(bridge, schema_resource)

            print("\n>>> Scenario 3: Incident Triage Grounded by MCP Prompts & Telemetry Resources")
            await run_scenario_3_incident_triage(bridge, schema_resource)

    finally:
        print("\n[*] Disconnecting from MCP Server...")
        await bridge.disconnect()
        print("[+] MCP Session cleanly closed.")


if __name__ == "__main__":
    asyncio.run(main())
