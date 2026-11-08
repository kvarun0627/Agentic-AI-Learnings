# Lab 03: The ReAct Agent (Reasoning + Acting)

This lab introduces the core foundation of autonomous agents: the **ReAct (Reason + Act)** loop.

---

## 1. Why ReAct?

In Phase 2, we built a **single-step tool calling engine**:
$$\text{User} \longrightarrow \text{LLM} \longrightarrow \text{Tool Call} \longrightarrow \text{Tool Result} \longrightarrow \text{Final Answer}$$

While powerful, single-turn dispatch cannot solve real-world backend tasks where **actions depend on intermediate observations**.

The **ReAct Pattern** introduces an iterative feedback loop:

```
                  +---------------------------+
                  |        User Goal          |
                  +-------------+-------------+
                                |
                                v
                +-----> [ 1. REASONING ] <------+
                |       Model evaluates state   |
                |       and chooses action      |
                |               |               |
[Goal Met / No Tools]           | [Needs Tools] |
                |               v               |
                |       [ 2. ACTION ]           |
                |       Execute Tool(s)         |
                |               |               |
                |               v               |
                |       [ 3. OBSERVATION ]      |
                |       Capture tool output     |
                |               |               |
                |               +---------------+
                v
    +-----------------------+
    |  Final Synthesis &    |
    |  Complete Response    |
    +-----------------------+
```

---

## 2. Key Architectural Components

### A. The Agent State / Scratchpad (`contents`)
In `google-genai`, conversation state is represented as a list of `types.Content` objects:
1. `role="user"`: Original prompt.
2. `role="model"`: Model candidate response (contains `function_calls` and optional reasoning text).
3. `role="user"`: One or more `Part.from_function_response` containing tool outputs.

Every step appends the turn's action and observation to this list. The model sees the entire history of what it tried and what happened.

### B. Termination Condition (`not response.function_calls`)
The loop continues until:
1. **The Model Finishes**: When the model has enough information, it stops generating `function_calls` and produces normal response text.
2. **Safety Guardrail (`max_steps`)**: Prevents infinite loops or runaway API charges if the model gets stuck.

### C. Parallel Tool Calling Support
If the model issues multiple function calls in one turn (e.g., checking two pods simultaneously), the loop iterates over `response.function_calls`, executes each, and packages all results into a single turn's response payload.

### D. Self-Correction & Error Resilience
If a tool raises an exception or returns `{"error": "..."}`, the loop does not crash. It formats the error as the tool observation. The model reads the error on the next step and adjusts its parameters or picks a different tool.

---

## 3. Running the Lab

Run the lab with:
```powershell
.\.venv\Scripts\python.exe .\03-react-agent\01_react_loop.py
```

### Verified Execution Trace
In the incident triage demo, the agent autonomously performed 5 sequential steps:
1. **Step 1**: Invoked `search_incidents("auth-service")` -> discovered active alert `ALT-9081` (CrashLoopBackOff).
2. **Step 2**: Inspected metrics of `auth-srv-101` -> verified healthy.
3. **Step 3**: Inspected metrics of `auth-srv-102` -> identified 99% CPU, 14 restarts, `CrashLoopBackOff`.
4. **Step 4**: Invoked `restart_pod("auth-service", "auth-srv-102")` -> restored pod health.
5. **Step 5**: Sent alert resolution message to `#oncall-eng` ops channel.
6. **Step 6**: Synthesized full incident report for human operators.
