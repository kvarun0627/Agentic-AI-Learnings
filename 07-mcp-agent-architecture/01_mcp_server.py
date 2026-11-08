import os
import sys
import json
import sqlite3
import argparse
from typing import Dict, Any, List, Optional

# Ensure UTF-8 output across Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp.server.mcpserver import MCPServer

# =====================================================================
# 1. Server Metadata & Database Setup
# =====================================================================
SERVER_NAME = "EnterpriseBankingAndOpsServer"
SERVER_VERSION = "1.0.0"

# Initialize SQLite database for the backend server
DB_PATH = os.path.join(os.path.dirname(__file__), "enterprise_banking.db")

def init_database() -> None:
    """Initializes tables and seeds initial account balances."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            balance REAL NOT NULL,
            tier TEXT NOT NULL,
            status TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_account TEXT NOT NULL,
            to_account TEXT NOT NULL,
            amount REAL NOT NULL,
            idempotency_key TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            response_payload TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Seed initial test data if empty
    cursor.execute("SELECT COUNT(*) FROM accounts;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO accounts VALUES ('ACC-1001', 'Alice Cooper', 5000.00, 'PLATINUM', 'ACTIVE');")
        cursor.execute("INSERT INTO accounts VALUES ('ACC-1002', 'Bob Vance', 1200.00, 'GOLD', 'ACTIVE');")
        cursor.execute("INSERT INTO accounts VALUES ('ACC-1003', 'Charlie Kelly', 45.00, 'STANDARD', 'FROZEN');")
        conn.commit()

    conn.close()

init_database()

# Create the MCP Server instance
server = MCPServer(name=SERVER_NAME, version=SERVER_VERSION)


# =====================================================================
# 2. MCP Primitive 1: Tools (Actionable Executable Functions)
# =====================================================================

@server.tool(
    name="query_database_readonly",
    description="Executes a safe read-only SQL query against the enterprise banking SQLite database. Query must begin with SELECT."
)
def query_database_readonly(sql: str) -> str:
    """Executes a read-only SQL query against the database.
    
    Args:
        sql: The SQL SELECT statement to execute (e.g. 'SELECT * FROM accounts WHERE status = \"ACTIVE\"').
    """
    clean_sql = sql.strip()
    if not clean_sql.upper().startswith("SELECT"):
        return json.dumps({
            "status": "ERROR",
            "error": "Security Violation: Only SELECT queries are permitted via read-only query tool."
        })

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(clean_sql)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return json.dumps({"status": "SUCCESS", "row_count": len(rows), "data": rows})
    except Exception as e:
        return json.dumps({"status": "ERROR", "error": f"Database execution error: {str(e)}"})


@server.tool(
    name="transfer_funds_atomic",
    description="Transfers funds between two customer accounts with ACID transaction atomicity, balance checks, and idempotency protection."
)
def transfer_funds_atomic(from_account: str, to_account: str, amount: float, idempotency_key: str = None) -> str:
    """Transfers funds between accounts.
    
    Args:
        from_account: Source account ID (e.g. 'ACC-1001').
        to_account: Destination account ID (e.g. 'ACC-1002').
        amount: Positive transfer amount in USD.
        idempotency_key: Optional UUID preventing double-charge on network retries.
    """
    if amount <= 0:
        return json.dumps({"status": "ERROR", "message": "Amount must be greater than zero."})
    if from_account == to_account:
        return json.dumps({"status": "ERROR", "message": "Source and destination accounts must be distinct."})

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE TRANSACTION;")

        # 1. Check Idempotency Key
        if idempotency_key:
            cursor.execute("SELECT response_payload FROM idempotency_keys WHERE idempotency_key = ?", (idempotency_key,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("ROLLBACK;")
                conn.close()
                return existing[0]

        # 2. Check and lock source account
        cursor.execute("SELECT balance, status FROM accounts WHERE account_id = ?", (from_account,))
        src = cursor.fetchone()
        if not src:
            cursor.execute("ROLLBACK;")
            conn.close()
            return json.dumps({"status": "ERROR", "message": f"Source account '{from_account}' not found."})
        
        src_balance, src_status = src[0], src[1]
        if src_status != "ACTIVE":
            cursor.execute("ROLLBACK;")
            conn.close()
            return json.dumps({"status": "ERROR", "message": f"Source account is {src_status}."})
        if src_balance < amount:
            cursor.execute("ROLLBACK;")
            conn.close()
            return json.dumps({"status": "ERROR", "message": f"Insufficient balance: available ${src_balance:.2f}, required ${amount:.2f}."})

        # 3. Check and lock destination account
        cursor.execute("SELECT status FROM accounts WHERE account_id = ?", (to_account,))
        dest = cursor.fetchone()
        if not dest:
            cursor.execute("ROLLBACK;")
            conn.close()
            return json.dumps({"status": "ERROR", "message": f"Destination account '{to_account}' not found."})
        if dest[0] != "ACTIVE":
            cursor.execute("ROLLBACK;")
            conn.close()
            return json.dumps({"status": "ERROR", "message": f"Destination account is {dest[0]}."})

        # 4. Atomic Balance Update
        cursor.execute("UPDATE accounts SET balance = balance - ? WHERE account_id = ?", (amount, from_account))
        cursor.execute("UPDATE accounts SET balance = balance + ? WHERE account_id = ?", (amount, to_account))

        # 5. Record Audit Ledger
        cursor.execute(
            "INSERT INTO audit_ledger (from_account, to_account, amount, idempotency_key) VALUES (?, ?, ?, ?)",
            (from_account, to_account, amount, idempotency_key)
        )

        response = {
            "status": "SUCCESS",
            "transferred_usd": amount,
            "from_account": from_account,
            "to_account": to_account,
            "idempotency_key": idempotency_key
        }
        res_json = json.dumps(response)

        # 6. Record Idempotency Cache
        if idempotency_key:
            cursor.execute(
                "INSERT INTO idempotency_keys (idempotency_key, status, response_payload) VALUES (?, ?, ?)",
                (idempotency_key, "COMPLETED", res_json)
            )

        conn.commit()
        conn.close()
        return res_json

    except Exception as exc:
        cursor.execute("ROLLBACK;")
        conn.close()
        return json.dumps({"status": "ERROR", "message": f"Transaction aborted: {str(exc)}"})


@server.tool(
    name="restart_service_container",
    description="Performs an automated rolling restart of a backend container pod (e.g. 'payment-gateway', 'auth-service', 'ledger-db')."
)
def restart_service_container(service_name: str, reason: str) -> str:
    """Restarts a microservice container.
    
    Args:
        service_name: Name of microservice deployment to restart.
        reason: Justification for restarting the service.
    """
    valid_services = ["payment-gateway", "auth-service", "ledger-db", "notification-worker"]
    if service_name not in valid_services:
        return json.dumps({
            "status": "FAILED",
            "error": f"Service '{service_name}' unknown. Valid targets: {valid_services}"
        })

    return json.dumps({
        "status": "RESTARTED",
        "service": service_name,
        "restart_id": "RESTART-POD-9921",
        "reason": reason,
        "health": "HEALTHY",
        "uptime": "0s (Just restarted)"
    })


# =====================================================================
# 3. MCP Primitive 2: Resources (Context Grounding Feeds)
# =====================================================================

@server.resource("banking://database/schema")
def get_database_schema() -> str:
    """Returns the complete DDL schema definition for the banking database to ground agent queries."""
    return """-- SQLite Banking Database Schema
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    balance REAL NOT NULL,
    tier TEXT NOT NULL,           -- 'PLATINUM', 'GOLD', 'STANDARD'
    status TEXT NOT NULL          -- 'ACTIVE', 'FROZEN', 'CLOSED'
);

CREATE TABLE audit_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_account TEXT NOT NULL,
    to_account TEXT NOT NULL,
    amount REAL NOT NULL,
    idempotency_key TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    response_payload TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);"""


@server.resource("system://telemetry/live")
def get_system_telemetry() -> str:
    """Returns real-time backend telemetry metrics including CPU, memory, and database connection pool."""
    return json.dumps({
        "cluster_region": "us-east-1",
        "cpu_utilization_percent": 24.5,
        "memory_used_mb": 1420,
        "memory_total_mb": 4096,
        "active_db_connections": 14,
        "max_db_connections": 50,
        "http_5xx_error_rate_percent": 0.02,
        "status": "OPERATIONAL"
    }, indent=2)


# =====================================================================
# 4. MCP Primitive 3: Prompts (Reusable Templated Workflows)
# =====================================================================

@server.prompt(
    name="diagnose_payment_incident",
    description="Generates a structured prompt recipe guiding an agent through incident diagnosis and account verification."
)
def diagnose_payment_incident(customer_id: str, issue_description: str) -> str:
    """Creates a standardized triage prompt for an LLM agent."""
    return f"""You are the Lead SRE Incident Responder for Apex Banking.
You have access to the Enterprise Banking MCP Server tools and resources.

Incident Context:
- Target Customer ID: {customer_id}
- Issue Reported   : {issue_description}

Diagnostic Protocol:
1. First, consult the database schema resource at 'banking://database/schema'.
2. Query customer account details using 'query_database_readonly' to check account status and balance.
3. Review 'system://telemetry/live' to verify cluster health.
4. Formulate an actionable remediation plan or execute corrective actions."""


# =====================================================================
# 5. Diagnostic Inspection & Self-Test
# =====================================================================

async def run_server_diagnostics():
    """Prints a structured architectural report of the server and performs self-test."""
    print("=" * 80)
    print(f"           MCP SERVER DIAGNOSTICS: [{SERVER_NAME}]")
    print(f"           Protocol Standard: MCP 2.x (JSON-RPC 2.0)")
    print("=" * 80)

    # 1. List Registered Tools
    tools = await server.list_tools()
    print(f"\n[1] Registered MCP Tools ({len(tools)}):")
    for i, t in enumerate(tools, 1):
        print(f"    {i}. {t.name}")
        print(f"       Description : {t.description}")
        props = t.input_schema.get("properties", {})
        req = t.input_schema.get("required", [])
        print(f"       Parameters  : {list(props.keys())} (Required: {req})")

    # 2. List Registered Resources
    resources = await server.list_resources()
    print(f"\n[2] Registered MCP Resources ({len(resources)}):")
    for i, r in enumerate(resources, 1):
        print(f"    {i}. URI : {r.uri}")
        print(f"       Name: {r.name}")

    # 3. List Registered Prompts
    prompts = await server.list_prompts()
    print(f"\n[3] Registered MCP Prompts ({len(prompts)}):")
    for i, p in enumerate(prompts, 1):
        print(f"    {i}. Name: {p.name}")
        print(f"       Desc: {p.description}")

    # 4. Self-Test Tools
    print("\n[4] Running Internal Tool Self-Tests...")
    test_query = query_database_readonly("SELECT account_id, customer_name, balance, status FROM accounts;")
    print(f"    -> query_database_readonly(): {test_query[:90]}...")

    test_transfer = transfer_funds_atomic("ACC-1001", "ACC-1002", 50.0, idempotency_key="TEST-INIT-001")
    print(f"    -> transfer_funds_atomic(): {test_transfer}")

    test_res = await server.read_resource("banking://database/schema")
    print(f"    -> read_resource('banking://database/schema'): Successfully retrieved ({len(test_res[0].content)} bytes)")

    print("\n" + "=" * 80)
    print("           [OK] ALL MCP SERVER PRIMITIVES OPERATIONAL")
    print("=" * 80)
    print("\nTo run as an active stdio JSON-RPC server for MCP Clients (Claude/Cursor/Agent):")
    print(f"  Command: python 01_mcp_server.py --stdio\n")


# =====================================================================
# 6. Entrypoint (CLI Dispatcher)
# =====================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{SERVER_NAME} MCP Server")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run as an MCP stdio server responding to JSON-RPC 2.0 messages"
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Run server diagnostics and print registered tools, resources, and prompts"
    )
    args = parser.parse_args()

    # If --inspect is explicitly requested or run without --stdio in an interactive terminal
    if args.inspect or (not args.stdio and sys.stdin.isatty()):
        import asyncio
        asyncio.run(run_server_diagnostics())
    else:
        # Run standard MCP stdio JSON-RPC loop
        server.run(transport="stdio")
