# Phase 06: Multi-Agent Systems & Collaboration

Welcome to Phase 6. In previous phases, you mastered:
1. **Tool Calling (`02-tool-calling-engine/`)**: Giving LLMs external capabilities.
2. **The ReAct Loop (`03-react-agent/`)**: Autonomous reason-act-observe loops.
3. **Memory & Context (`04-memory-and-rag/`)**: Context window budgeting and semantic retrieval.
4. **Stateful Workflows (`05-stateful-workflows/`)**: Graph-based state machines, cyclical self-correction, and durable HITL checkpointing.

---

## 1. Why Multi-Agent Systems? (The Microservices Analogy)

In traditional backend engineering, monolithic architectures work well initially, but as features grow, they become difficult to maintain, test, and scale. We decompose monoliths into **microservices** with single responsibilities.

Similarly, in agentic architectures:
- **A Single "Do-It-All" Agent is a Monolith**: Giving an LLM 30 tools and a 4-page system prompt leads to prompt confusion, tool hallucination, and context blowup.
- **Multi-Agent Systems are Microservices**: We break the problem down into small, specialized agents (e.g., *Database Specialist*, *Network Specialist*, *Security Reviewer*). Each agent has:
  1. A narrow, well-defined persona.
  2. Access only to tools relevant to its domain.
  3. A clean input/output interface to communicate with other agents or a central orchestrator.

---

## 2. Core Multi-Agent Collaboration Patterns

```
Pattern 1: Hierarchical (Supervisor)    Pattern 2: Peer-to-Peer (Handoffs)     Pattern 3: Multi-Agent Debate
         ┌────────────┐                         ┌─────────┐                         ┌─────────┐
         │ Supervisor │                         │ Triage  │                         │ Creator │
         └─────┬──────┘                         └────┬────┘                         └────┬────┘
      ┌────────┴────────┐                            │ (handoff)                         ▲    │ (propose)
      ▼                 ▼                            ▼                                   │    ▼
┌───────────┐     ┌───────────┐                 ┌─────────┐                         ┌────┴────┐
│ DB Worker │     │ Sec Worker│                 │ Billing │                         │ Critic  │
└───────────┘     └───────────┘                 └─────────┘                         └─────────┘
```

1. **Hierarchical (Supervisor-Worker)**:
   A central coordinator agent (Incident Commander) evaluates the overall mission, breaks it into subtasks, delegates to specialized worker agents, collects results, and decides when the mission is accomplished.
2. **Decentralized Handoffs (Swarm / Router)**:
   Agents pass control directly to peers without returning to a central manager (e.g., Customer Support Triage hands off to Billing Agent, who hands off to Refund Agent).
3. **Adversarial Debate / Consensus (Maker-Checker)**:
   Agents with differing objectives review each other's work (e.g., Code Generator vs. Security Auditor) iteratively until standards are satisfied.

---

## 3. Phase 6 Project Roadmap

| Lab | Script | Pattern | Focus |
| :--- | :--- | :--- | :--- |
| **Lab 01** | `01_supervisor_orchestrator.py` | **Supervisor-Worker** | Central SRE Incident Commander routing tasks cyclically between DB, Network, and Infrastructure specialist agents. | Completed |
| **Lab 02** | `02_agent_handoffs_swarm.py` | **Decentralized Handoffs** | Peer-to-peer control transfer via dynamic tool-based handoffs (The Swarm pattern). | Completed |
| **Lab 03** | `03_adversarial_code_review.py` | **Maker-Checker Debate** | Autonomous adversarial debate between Developer Agent and Red-Team Security Auditor. | Completed |

---

## 4. Architectural Comparison: Supervisor vs. Swarm Handoffs

| Feature | Lab 01: Hierarchical Supervisor | Lab 02: Decentralized Swarm (Handoffs) |
| :--- | :--- | :--- |
| **Control Topology** | Centralized Star ($\text{Agent}_i \leftrightarrow \text{Supervisor}$) | Peer-to-Peer Pipeline ($\text{Agent}_A \rightarrow \text{Agent}_B \rightarrow \text{Agent}_C$) |
| **LLM Call Overhead** | High (2 LLM calls per worker step: Supervisor + Worker) | Low (1 LLM call per step; active agent directly transfers) |
| **Context Window** | Supervisor accumulates history of all workers (Context bloat) | Decoupled; each agent only receives ticket + handover notes |
| **Routing Mechanism** | Structured JSON schema decision emitted by Supervisor | First-class Handoff Tools (`transfer_to_*`) emitted by agents |
| **Backend Analogy** | Saga Orchestrator / Central API Gateway | Event Choreography / Pipeline Filter / Call Transfer Protocol |

