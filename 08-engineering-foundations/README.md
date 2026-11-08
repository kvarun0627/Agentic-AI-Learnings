# Phase 08: Engineering Foundations

Phases 1–7 taught how agents work. This phase sets up the ground that every later production practice (evals, tracing, security, deployment) is built on.

| Lesson | Topic | Status |
| :--- | :--- | :--- |
| **8.1** | Reproducibility: version control and pinned dependencies | In Progress |
| **8.2** | A shared LLM gateway: one place where every model call goes | Not Started |
| **8.3** | Dependency injection and testing agents with a fake LLM | Not Started |

---

## Lesson 8.1: Reproducibility

### 1. Why is this needed?

In a normal backend service, behavior changes when **code** changes. In an agent, behavior changes when any of these change:

| What changes | Example from your repo | Visible in a code diff? |
| :--- | :--- | :--- |
| Code | `run_react_agent` loop logic | Yes |
| **Prompts** | `SYSTEM_INSTRUCTION` in `03_react_loop.py` | Only if versioned |
| **Tool descriptions** | The docstrings on `restart_pod` (the model reads these!) | Only if versioned |
| **Model version** | `gemini-3.5-flash-lite` silently updated by the provider | No |
| **SDK version** | `google-genai` 2.29 → 3.0 changes how `function_calls` parse | Only if pinned |
| Temperature / config | `temperature=0.0` | Only if versioned |

**The production failure this prevents:** On Monday your SRE agent restarts the right pod. On Friday it starts restarting healthy pods. You ask "what changed?" and can't answer, because:
- there is no git history to diff the prompt or tool docstrings against,
- `pip install google-genai` pulled a newer SDK on the new machine,
- you can't reproduce Monday's environment to compare.

Key mental shift: **prompts and tool docstrings are source code.** A one-word change in a tool description can change which tool the model picks. They need the same history, review and rollback as Java code.

**Java analogy:** This is Maven's `pom.xml` with exact versions plus Git. You would never ship a Spring Boot service with `<version>LATEST</version>` and no source control. Right now this repo is effectively doing that.

### 2. How it's done

Three pieces:

1. **Git**: history for code, prompts and tool descriptions. Every behavior change becomes a reviewable diff.
2. **`pyproject.toml`**: the Python `pom.xml`. It declares the project's direct dependencies with **exact pinned versions**.
3. **`.gitignore`** that excludes:
   - **secrets** (`.env`): a committed API key is a security incident, even if you delete it later, because it stays in git history;
   - **runtime state** (`*.db`): checkpoint and banking databases are data, not source;
   - **environments** (`.venv/`): they are rebuilt from `pyproject.toml`, never copied.

On top of that:

| Concept | Why |
| :--- | :--- |
| **Pin model IDs in config, not scattered in code** | `MODEL_NAME = "gemini-3.5-flash-lite"` is currently copy-pasted into ~15 files. Upgrading the model means hunting through all of them. (Fixed properly in Lesson 8.2.) |
| **Lockfile (`uv.lock` / `pip freeze`)** | `pyproject.toml` pins your *direct* deps. A lockfile pins the *transitive* ones too (`httpx`, `anyio` …), giving a byte-for-byte rebuildable environment. |

**About `uv`:** `uv` is the modern Python package manager, similar to Maven or Gradle, and 10–100× faster than pip. It produces a cross-platform lockfile. It's the current industry standard, and installing it is part of the exercise below.

### 3. Lab: files created

- `pyproject.toml` (repo root): project metadata, Python version, pinned direct dependencies, dev tools.
- `.gitignore` (updated): now also ignores `*.db`, caches and editor folders.

### 4. Exercise: do these yourself

Run each step with `! <command>` in Claude Code or in your own terminal, from `D:\Agentic AI`.

1. **Initialize git and check that secrets are excluded**
   ```bash
   git init
   git status
   ```
   ✅ Check: `.env` and the `*.db` files must **not** appear in the `git status` list. If `.env` appears, stop and fix `.gitignore` first.

2. **Make your first commit**
   ```bash
   git add .
   git commit -m "Phase 1-7 learning labs + Part II roadmap"
   ```

3. **Prove that prompts are code.** Open `03-react-agent/01_react_loop.py` and change the `restart_pod` docstring to `"""Restart a pod. Only use this as a last resort after the user explicitly confirms."""`. Run the agent. Then run:
   ```bash
   git diff
   ```
   Note whether the agent still restarted the pod, and compare that with the diff. Revert with `git checkout -- 03-react-agent/01_react_loop.py`.

4. **(Recommended) Install uv and lock the environment**
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   uv lock
   ```
   This creates `uv.lock`. Commit it.

5. **Answer in your own words** (write the answers below in this README):
   - Why is a changed tool *docstring* a behavior change, while a renamed local variable isn't?
   - Your `.env` was committed in commit #3 and deleted in commit #4. Is the key safe? Why or why not?

### 5. My answers & observations

_(Fill in after doing the exercise.)_

- SDK with read tool name , function docstrings , function argument into a schema and send it to LLM , changing anything in this will change how the LLM responds. but a local varial is not read by LLM , it stays within the code so changing it does not change the output.

- No the key is not safe any can go thorough the git history and look into the key which raises security concerns. we need to revoke the push history and terminate the key to stay safe.



