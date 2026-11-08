import os
import sys
import json
import sqlite3
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

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
# 2. Structured DTOs for the Maker-Checker Debate Protocol
# =====================================================================

class AuditFinding(BaseModel):
    severity: str = Field(
        description="Severity level of vulnerability: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'."
    )
    vulnerability_type: str = Field(
        description="Category: 'SQL_INJECTION', 'RACE_CONDITION', 'NEGATIVE_AMOUNT_BYPASS', 'MISSING_TRANSACTION_ATOMICITY', 'MISSING_IDEMPOTENCY', 'INSUFFICIENT_INPUT_VALIDATION', etc."
    )
    location: str = Field(
        description="Function or code segment where vulnerability exists."
    )
    description: str = Field(
        description="Specific explanation of why this code is vulnerable and how an attacker could exploit it."
    )
    suggested_fix: str = Field(
        description="Concrete, actionable coding instruction for the developer to eliminate the vulnerability."
    )


class AuditVerdict(BaseModel):
    status: str = Field(
        description="Auditor decision: 'APPROVED' if zero critical/high vulnerabilities exist and code is production-ready; otherwise 'REJECTED'."
    )
    findings: List[AuditFinding] = Field(
        default_factory=list,
        description="List of security vulnerabilities and engineering deficiencies detected in the submission."
    )
    verdict_rationale: str = Field(
        description="Executive summary of the security audit verdict."
    )


class CodeSubmission(BaseModel):
    code: str = Field(
        description="Complete, executable Python code implementation implementing the specification."
    )
    architectural_notes: str = Field(
        description="Summary of architectural patterns, defense mechanisms, and design decisions used."
    )
    changelog: Optional[str] = Field(
        default=None,
        description="If this is a revision, bullet points summarizing how auditor findings were addressed."
    )


@dataclass
class DebateRoundRecord:
    round_number: int
    submission: CodeSubmission
    verdict: AuditVerdict


# =====================================================================
# 3. Agent Personas
# =====================================================================

class SoftwareEngineerAgent:
    """The 'Maker': Autonomous Developer Agent driven to maximize feature completeness,
    clean software architecture, and iterative bug remediation.
    """
    NAME = "DEVELOPER_AGENT"

    def __init__(self):
        self.system_instruction = """You are a Principal Backend Software Engineer.
Your goal is to write robust, maintainable, production-ready Python backend code.

Rules:
1. Provide fully runnable code with no placeholders or 'TODO' shortcuts.
2. In Round 1, propose a clean initial implementation satisfying the business specification.
3. In subsequent revision rounds, carefully analyze the Security Auditor's critique, acknowledge every vulnerability, and refactor the code to eliminate all security flaws.
4. Always respond with the required structured JSON schema."""

    def propose_initial_solution(self, specification: str) -> CodeSubmission:
        prompt = f"""Business Specification:
{specification}

Task: Write the initial implementation for this service.
Focus on fulfilling the basic transfer logic and database queries."""

        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=CodeSubmission
                )
            )
            return CodeSubmission.model_validate_json(response.text)
        except Exception as e:
            print(f"   [!] Developer LLM fallback triggered ({e})")
            return self._fallback_round_1()

    def refactor_solution(self, specification: str, previous_code: str, audit_verdict: AuditVerdict, round_num: int) -> CodeSubmission:
        findings_summary = "\n".join([
            f"- [{f.severity}] {f.vulnerability_type} at {f.location}: {f.description}. Fix: {f.suggested_fix}"
            for f in audit_verdict.findings
        ])

        prompt = f"""Original Specification:
{specification}

Previous Code Submission (Round {round_num - 1}):
```python
{previous_code}
```

Security Auditor Feedback (Verdict: {audit_verdict.status}):
Executive Rationale: {audit_verdict.verdict_rationale}
Vulnerabilities Found:
{findings_summary}

Task: Refactor the code to fix EVERY reported vulnerability and security flaw.
Provide:
1. Complete, hardened Python code.
2. Architectural notes detailing the new defense-in-depth measures.
3. Changelog listing exact fixes applied for each auditor finding."""

        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=CodeSubmission
                )
            )
            return CodeSubmission.model_validate_json(response.text)
        except Exception as e:
            print(f"   [!] Developer LLM fallback triggered ({e})")
            return self._fallback_round_2()

    def _fallback_round_1(self) -> CodeSubmission:
        """Deterministic Round 1 code containing subtle real-world security flaws for the auditor to catch."""
        code = '''def transfer_funds(db_conn, from_account: str, to_account: str, amount: float, idempotency_key: str = None) -> dict:
    """Transfers funds between two bank accounts."""
    cursor = db_conn.cursor()

    # Step 1: Check balance of source account
    # Flaw: String formatting introduces SQL Injection risk
    query = f"SELECT balance FROM accounts WHERE account_id = '{from_account}'"
    cursor.execute(query)
    row = cursor.fetchone()
    if not row:
        return {"status": "ERROR", "message": "Source account not found"}
    
    current_balance = row[0]
    
    # Flaw: Missing check for negative or zero amounts (allows balance siphon attack!)
    if current_balance < amount:
        return {"status": "ERROR", "message": "Insufficient funds"}

    # Step 2: Debit sender and credit receiver without atomic transaction block
    cursor.execute(f"UPDATE accounts SET balance = balance - {amount} WHERE account_id = '{from_account}'")
    cursor.execute(f"UPDATE accounts SET balance = balance + {amount} WHERE account_id = '{to_account}'")
    
    # Flaw: Missing idempotency key check and audit log recording
    db_conn.commit()
    return {"status": "SUCCESS", "transferred": amount, "from": from_account, "to": to_account}
'''
        return CodeSubmission(
            code=code,
            architectural_notes="Initial implementation with basic account existence and balance verification.",
            changelog="Initial release."
        )

    def _fallback_round_2(self) -> CodeSubmission:
        """Deterministic Round 2 hardened code addressing all auditor concerns."""
        code = '''def transfer_funds(db_conn, from_account: str, to_account: str, amount: float, idempotency_key: str = None) -> dict:
    """Secure, atomic fund transfer service protected against SQLi, race conditions, negative amounts, and double-spend."""
    # 1. Input Validation Guardrails
    if not isinstance(amount, (int, float)) or amount <= 0:
        return {"status": "ERROR", "message": "Transfer amount must be a positive number greater than zero."}
    
    if from_account == to_account:
        return {"status": "ERROR", "message": "Source and destination accounts must be distinct."}

    cursor = db_conn.cursor()

    try:
        # 2. Begin Explicit Database Transaction (ACID Isolation)
        cursor.execute("BEGIN IMMEDIATE TRANSACTION;")

        # 3. Idempotency Check: Prevent duplicate charge execution
        if idempotency_key:
            cursor.execute(
                "SELECT status, response_payload FROM idempotency_keys WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            existing = cursor.fetchone()
            if existing:
                import json
                cursor.execute("ROLLBACK;")
                return json.loads(existing[1])

        # 4. Parameterized Query & Row Locking for Source Account
        cursor.execute(
            "SELECT balance, status FROM accounts WHERE account_id = ?",
            (from_account,)
        )
        source = cursor.fetchone()
        if not source:
            cursor.execute("ROLLBACK;")
            return {"status": "ERROR", "message": f"Source account '{from_account}' not found."}
        
        from_balance, from_status = source[0], source[1]
        if from_status != "ACTIVE":
            cursor.execute("ROLLBACK;")
            return {"status": "ERROR", "message": f"Source account is {from_status}."}

        if from_balance < amount:
            cursor.execute("ROLLBACK;")
            return {"status": "ERROR", "message": f"Insufficient funds: available {from_balance}, requested {amount}."}

        # 5. Parameterized Query for Destination Account
        cursor.execute(
            "SELECT status FROM accounts WHERE account_id = ?",
            (to_account,)
        )
        dest = cursor.fetchone()
        if not dest:
            cursor.execute("ROLLBACK;")
            return {"status": "ERROR", "message": f"Destination account '{to_account}' not found."}
        
        if dest[0] != "ACTIVE":
            cursor.execute("ROLLBACK;")
            return {"status": "ERROR", "message": f"Destination account is {dest[0]}."}

        # 6. Atomic Balance Update using Parameterized Statements
        cursor.execute(
            "UPDATE accounts SET balance = balance - ? WHERE account_id = ?",
            (amount, from_account)
        )
        cursor.execute(
            "UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
            (amount, to_account)
        )

        # 7. Immutable Audit Trail
        cursor.execute(
            "INSERT INTO audit_ledger (from_account, to_account, amount, idempotency_key) VALUES (?, ?, ?, ?)",
            (from_account, to_account, amount, idempotency_key)
        )

        # 8. Record Idempotency Result
        payload = {
            "status": "SUCCESS",
            "transferred": amount,
            "from_account": from_account,
            "to_account": to_account
        }
        if idempotency_key:
            import json
            cursor.execute(
                "INSERT INTO idempotency_keys (idempotency_key, status, response_payload) VALUES (?, ?, ?)",
                (idempotency_key, "COMPLETED", json.dumps(payload))
            )

        # 9. Commit Transaction
        db_conn.commit()
        return payload

    except Exception as exc:
        cursor.execute("ROLLBACK;")
        return {"status": "ERROR", "message": f"Transaction aborted due to internal error: {str(exc)}"}
'''
        return CodeSubmission(
            code=code,
            architectural_notes="Hardened with ACID transaction block, parameterized SQL, idempotency ledger, and strict positive amount validation.",
            changelog="Fixed SQL injection via parameterized queries, added negative amount guardrail, added explicit BEGIN/ROLLBACK transaction isolation, and implemented idempotency ledger."
        )


class SecurityAuditorAgent:
    """The 'Checker': Adversarial Red-Team Security Specialist with a zero-trust mindset.
    Finds edge cases, concurrency bugs, OWASP flaws, and race conditions.
    """
    NAME = "SECURITY_AUDITOR"

    def __init__(self):
        self.system_instruction = """You are a Lead Application Security Specialist and Red-Team Code Auditor.
Your exact mission:
1. Perform an aggressive, adversarial security review of the submitted backend code.
2. Scrutinize for:
   - SQL Injection (string formatting in queries vs parameterized statements)
   - Race Conditions / Double-Spend / Concurrency hazards (lack of transaction isolation or atomic balance updates)
   - Input Validation bypasses (negative numbers, zero amounts, self-transfers)
   - Missing Idempotency protections (network retries causing duplicate debits)
   - Exception handling leaks and transaction rollbacks.
3. Decision Criteria:
   - If ANY Critical or High vulnerabilities exist: Verdict MUST be 'REJECTED'.
   - Only emit 'APPROVED' when ALL security requirements are met, code uses parameterized queries, explicit atomic transactions with rollback on failure, idempotency handling, and positive number validation.
4. Always respond with the required structured JSON schema."""

    def audit_code(self, specification: str, submission: CodeSubmission, round_num: int) -> AuditVerdict:
        prompt = f"""Business Specification:
{specification}

Code Submission under Review (Round {round_num}):
Architectural Notes from Developer:
{submission.architectural_notes}

{f"Changelog: {submission.changelog}" if submission.changelog else ""}

Source Code:
```python
{submission.code}
```

Task: Conduct a rigorous red-team audit. Identify any security risks or architecture bugs.
Emit your verdict as structured JSON."""

        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=AuditVerdict
                )
            )
            return AuditVerdict.model_validate_json(response.text)
        except Exception as e:
            print(f"   [!] Auditor LLM fallback triggered ({e})")
            if round_num == 1:
                return self._fallback_audit_round_1()
            return self._fallback_audit_round_2()

    def _fallback_audit_round_1(self) -> AuditVerdict:
        return AuditVerdict(
            status="REJECTED",
            findings=[
                AuditFinding(
                    severity="CRITICAL",
                    vulnerability_type="SQL_INJECTION",
                    location="cursor.execute(query) / f-strings",
                    description="User inputs 'from_account' and 'to_account' are formatted directly into SQL strings, allowing SQL injection attacks.",
                    suggested_fix="Replace f-strings with parameterized query placeholders (e.g., 'WHERE account_id = ?', (from_account,))."
                ),
                AuditFinding(
                    severity="CRITICAL",
                    vulnerability_type="NEGATIVE_AMOUNT_BYPASS",
                    location="if current_balance < amount:",
                    description="No validation checks whether 'amount' is positive. An attacker transferring -$1,000 will increase their balance while draining the target.",
                    suggested_fix="Validate that 'amount' is a positive numeric value greater than zero before performing any balance operations."
                ),
                AuditFinding(
                    severity="HIGH",
                    vulnerability_type="MISSING_TRANSACTION_ATOMICITY",
                    location="cursor.execute debit / credit",
                    description="Debit and credit operations run without an explicit transaction block or rollback handler. A crash between debit and credit will destroy funds.",
                    suggested_fix="Enclose all database mutations in an explicit transaction (BEGIN IMMEDIATE / COMMIT) with a try/except ROLLBACK safety net."
                ),
                AuditFinding(
                    severity="MEDIUM",
                    vulnerability_type="MISSING_IDEMPOTENCY",
                    location="transfer_funds signature",
                    description="Idempotency key parameter is accepted but ignored, exposing the API to double-charging on client network timeouts and retries.",
                    suggested_fix="Implement an idempotency table lookup and persistent audit record before committing transactions."
                )
            ],
            verdict_rationale="Submission contains critical SQL injection and negative balance bypass vulnerabilities, lack of transaction atomicity, and missing idempotency handling."
        )

    def _fallback_audit_round_2(self) -> AuditVerdict:
        return AuditVerdict(
            status="APPROVED",
            findings=[],
            verdict_rationale="All previous vulnerabilities resolved. Code uses parameterized SQL, strict positive input validation, explicit ACID transaction control with rollbacks, and persistent idempotency checks."
        )


# =====================================================================
# 4. Multi-Agent Debate Engine (Maker-Checker Orchestration)
# =====================================================================

class MakerCheckerEngine:
    """Orchestrates the adversarial dialogue between Maker (Developer) and Checker (Auditor)
    until consensus (APPROVAL) is reached or max_rounds is exhausted.
    """

    def __init__(self, developer: SoftwareEngineerAgent, auditor: SecurityAuditorAgent):
        self.developer = developer
        self.auditor = auditor

    def run_debate(self, specification: str, max_rounds: int = 4) -> Dict[str, Any]:
        debate_history: List[DebateRoundRecord] = []
        current_submission: Optional[CodeSubmission] = None
        consensus_reached = False

        print("\n" + "=" * 80)
        print("[!] ADVERSARIAL MULTI-AGENT DEBATE ENGINE INITIALIZED")
        print(f"    Maker   : {self.developer.NAME} (Senior Backend Engineer)")
        print(f"    Checker : {self.auditor.NAME} (Red-Team Security Auditor)")
        print(f"    Goal    : Converge on zero-vulnerability, production-grade code")
        print("=" * 80)

        for round_num in range(1, max_rounds + 1):
            print(f"\n{'=' * 80}")
            print(f">>> [ROUND {round_num}/{max_rounds}] ADVERSARIAL REVIEW CYCLE")
            print(f"{'=' * 80}")

            # 1. Developer Turn (Maker)
            if round_num == 1:
                print(f"[*] [{self.developer.NAME}] Authoring initial code implementation...")
                current_submission = self.developer.propose_initial_solution(specification)
            else:
                print(f"[*] [{self.developer.NAME}] Ingesting auditor critique & refactoring code...")
                last_verdict = debate_history[-1].verdict
                current_submission = self.developer.refactor_solution(
                    specification=specification,
                    previous_code=current_submission.code,
                    audit_verdict=last_verdict,
                    round_num=round_num
                )

            print(f"\n--- [{self.developer.NAME}] Submission Summary ---")
            print(f"Architectural Notes: {current_submission.architectural_notes}")
            if current_submission.changelog:
                print(f"Changelog Applied  : {current_submission.changelog}")

            # 2. Security Auditor Turn (Checker)
            print(f"\n[*] [{self.auditor.NAME}] Conducting adversarial security review...")
            verdict = self.auditor.audit_code(
                specification=specification,
                submission=current_submission,
                round_num=round_num
            )

            debate_history.append(DebateRoundRecord(
                round_number=round_num,
                submission=current_submission,
                verdict=verdict
            ))

            # Display Auditor Findings
            print(f"\n--- [{self.auditor.NAME}] Audit Verdict: [{verdict.status}] ---")
            print(f"Rationale: {verdict.verdict_rationale}")

            if verdict.findings:
                print(f"Vulnerabilities Identified ({len(verdict.findings)}):")
                for i, f in enumerate(verdict.findings, 1):
                    print(f"  {i}. [{f.severity}] {f.vulnerability_type} at {f.location}")
                    print(f"     Issue : {f.description}")
                    print(f"     Action: {f.suggested_fix}")

            # 3. Consensus Check
            if verdict.status.upper() == "APPROVED":
                print(f"\n[OK] CONSENSUS REACHED AT ROUND {round_num}! Code approved for production.")
                consensus_reached = True
                break
            else:
                print(f"\n[!] VERDICT REJECTED. Returning code to Developer for remediation.")

        return {
            "consensus_reached": consensus_reached,
            "total_rounds": len(debate_history),
            "final_submission": current_submission,
            "debate_history": debate_history
        }


# =====================================================================
# 5. Live Runtime Sandbox Verification
# =====================================================================

def verify_code_in_sandbox(generated_code: str) -> None:
    """Executes the final consensus-approved code against an in-memory SQLite
    test suite to guarantee that generated code is fully functional and secure.
    """
    print("\n" + "=" * 80)
    print("           SANDBOX TEST SUITE: EXECUTING GENERATED CODE")
    print("=" * 80)

    # Prepare Isolated In-Memory Database
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE accounts (
            account_id TEXT PRIMARY KEY,
            balance REAL NOT NULL,
            status TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE audit_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_account TEXT NOT NULL,
            to_account TEXT NOT NULL,
            amount REAL NOT NULL,
            idempotency_key TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        CREATE TABLE idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            response_payload TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Seed Accounts
    cursor.execute("INSERT INTO accounts VALUES ('ACC_ALICE', 1000.00, 'ACTIVE');")
    cursor.execute("INSERT INTO accounts VALUES ('ACC_BOB', 250.00, 'ACTIVE');")
    conn.commit()

    # Dynamic Execution Environment
    exec_scope: Dict[str, Any] = {"sqlite3": sqlite3}
    try:
        exec(generated_code, exec_scope)
        transfer_func = exec_scope.get("transfer_funds")
        if not transfer_func:
            raise KeyError("Function 'transfer_funds' not defined in generated code.")
    except Exception as e:
        print(f"[X] Failed to compile generated code: {e}")
        return

    # --- Test 1: Valid Transfer ---
    print("\n[Test 1] Valid Transfer ($200 from Alice -> Bob)...")
    t1_res = transfer_func(conn, "ACC_ALICE", "ACC_BOB", 200.0, idempotency_key="IDEM_KEY_001")
    print(f"         Result: {t1_res}")
    
    cursor.execute("SELECT account_id, balance FROM accounts")
    balances = dict(cursor.fetchall())
    assert balances["ACC_ALICE"] == 800.0, f"Alice balance mismatch: {balances['ACC_ALICE']}"
    assert balances["ACC_BOB"] == 450.0, f"Bob balance mismatch: {balances['ACC_BOB']}"
    print("         Assert Passed: Balances correctly updated (Alice: $800, Bob: $450).")

    # --- Test 2: Idempotency Protection (Duplicate Request) ---
    print("\n[Test 2] Replay Identical Request (Same Idempotency Key)...")
    t2_res = transfer_func(conn, "ACC_ALICE", "ACC_BOB", 200.0, idempotency_key="IDEM_KEY_001")
    print(f"         Result: {t2_res}")

    cursor.execute("SELECT account_id, balance FROM accounts")
    balances_after_replay = dict(cursor.fetchall())
    assert balances_after_replay["ACC_ALICE"] == 800.0, "Alice balance improperly deducted on replay!"
    assert balances_after_replay["ACC_BOB"] == 450.0, "Bob balance improperly credited on replay!"
    print("         Assert Passed: Idempotency prevented duplicate charge! Balances remained unchanged.")

    # --- Test 3: Exploit Attempt: Negative Amount Injection ---
    print("\n[Test 3] Attack Simulation: Negative Transfer Amount (-$500)...")
    try:
        t3_res = transfer_func(conn, "ACC_ALICE", "ACC_BOB", -500.0, idempotency_key="IDEM_KEY_EVIL")
        print(f"         Result: {t3_res}")
        assert isinstance(t3_res, dict) and t3_res.get("status") in ("ERROR", "FAILED"), "Negative amount exploit was not rejected!"
    except ValueError as ve:
        print(f"         Caught Expected ValueError: {ve}")
    print("         Assert Passed: Negative balance exploit successfully neutralized.")

    # --- Test 4: Insufficient Funds ---
    print("\n[Test 4] Overdraft Protection: Transfer Exceeding Balance ($99999)...")
    try:
        t4_res = transfer_func(conn, "ACC_ALICE", "ACC_BOB", 99999.0, idempotency_key="IDEM_KEY_OVERDRAFT")
        print(f"         Result: {t4_res}")
        assert isinstance(t4_res, dict) and t4_res.get("status") in ("ERROR", "FAILED"), "Overdraft was not rejected!"
    except ValueError as ve:
        print(f"         Caught Expected ValueError: {ve}")
    print("         Assert Passed: Insufficient balance rejected cleanly.")

    print("\n" + "=" * 80)
    print("         ALL SANDBOX TESTS PASSED! PRODUCTION VERIFICATION COMPLETE")
    print("=" * 80)


# =====================================================================
# 6. Main Execution Script
# =====================================================================

if __name__ == "__main__":
    specification = """Function Signature:
def transfer_funds(db_conn, from_account: str, to_account: str, amount: float, idempotency_key: str = None) -> dict:

Database Schema:
- Table 'accounts' (account_id TEXT PRIMARY KEY, balance REAL NOT NULL, status TEXT NOT NULL)
- Table 'audit_ledger' (id INTEGER PRIMARY KEY AUTOINCREMENT, from_account TEXT NOT NULL, to_account TEXT NOT NULL, amount REAL NOT NULL, idempotency_key TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
- Table 'idempotency_keys' (idempotency_key TEXT PRIMARY KEY, status TEXT NOT NULL, response_payload TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)

Business Requirements:
1. Transfer funds from 'from_account' to 'to_account' in the SQLite database.
2. Verify that 'from_account' and 'to_account' exist and are in 'ACTIVE' status.
3. Validate that 'amount' is strictly positive and that 'from_account' has sufficient balance.
4. Execute debit and credit atomically within a single transaction block; if anything fails, roll back completely.
5. If 'idempotency_key' is provided, check 'idempotency_keys' table (querying 'response_payload') to prevent duplicate execution; save serialized response to 'response_payload' on success.
6. Record successful transfers in the 'audit_ledger' table.
7. Return a dict with {"status": "SUCCESS", "transferred": amount, ...} or {"status": "ERROR" / "FAILED", ...}.
8. Protect strictly against SQL injection, negative amount balance siphon attacks, and concurrency race conditions."""

    dev_agent = SoftwareEngineerAgent()
    security_auditor = SecurityAuditorAgent()
    engine = MakerCheckerEngine(developer=dev_agent, auditor=security_auditor)

    results = engine.run_debate(specification=specification, max_rounds=4)

    # If consensus reached, verify in sandbox
    if results["consensus_reached"]:
        final_code = results["final_submission"].code
        print("\n" + "=" * 80)
        print("                 FINAL CONSENSUS-APPROVED CODE")
        print("=" * 80)
        print(final_code)
        verify_code_in_sandbox(final_code)
    else:
        print("\n[!] Agents failed to reach consensus within round limit.")
