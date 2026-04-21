# Microsoft Foundry Workshop — Hands-On Lab

## Overview

This hands-on lab walks you through building AI agents using Microsoft Foundry,
from infrastructure deployment to multi-agent orchestration. The workshop is
split into six progressive notebooks that provision Azure resources, configure
tracing, and guide you through increasingly advanced agent patterns.

## Prerequisites

| Requirement | How to verify |
|-------------|---------------|
| **Python 3.10+** | `python --version` |
| **uv** (package manager) | `uv version` |
| **Azure CLI** | `az version` |
| **Azure subscription** | `az account show` |
| **Logged in** | `az login` (run before starting) |

### Installing uv

If you don't have `uv` yet:

```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> Notebook `00-setup.ipynb` validates all prerequisites automatically in its first cells.

## Quick Start

1. **Clone or download** this folder to your local machine.
2. **Open** the folder in VS Code.
3. **Open** `00-setup.ipynb`.
4. **Run the first code cell** — it creates a `.venv` and installs all dependencies using `uv`.
5. **Select the `.venv` kernel** — click "Select Kernel" in the top-right, choose "Python Environments…", and pick `.venv`.
6. **Choose your path:**
   - **Self-deployed infrastructure** — run Section 0A cells sequentially to deploy all Azure resources via Bicep.
   - **Pre-provisioned resources** — run the **Optional** cell (right after prerequisite validation) to connect to an existing Foundry resource and deploy App Insights. Then skip Section 0A.
7. **Run Section 0B cells** (Verify Virtual Environment → Imports & Authentication → Verify Connectivity).
8. **Proceed through the remaining notebooks in order** (`01` → `02` → `03` → `04` → `05`).
9. **Optionally**, run `e2e-agent-lifecycle.ipynb` for a full lifecycle demo (create → test → trace → evaluate → publish → monitor).

### Using Pre-Provisioned Resources

If your organization already has an AI Foundry resource with model deployments and RBAC assigned:

1. In `00-setup.ipynb`, run the **Prerequisite Validation** cell first.
2. Edit the 4 variables in the **Optional** cell (resource group, account name, project name, model deployment).
3. Run the cell — it will connect to your existing resource, deploy App Insights if needed (or reuse an existing one), and save the config to `workshop_config.json`.
4. **Skip Section 0A entirely** and continue with Section 0B.
5. All other notebooks automatically detect `workshop_config.json` and use your pre-provisioned resources.

## Workshop Structure

| Notebook | Duration | Topics |
|----------|----------|--------|
| **00-setup.ipynb** | ~10 min | Prerequisites validation, Azure infrastructure deployment (AI Services, models, App Insights), tracing setup. Optional cell for pre-provisioned environments. |
| **01-first-agent.ipynb** | ~8 min | Your first Foundry agent — create, chat, multi-turn, grounding with MCP |
| **02-tools.ipynb** | ~10 min | Tool usage — function calling, web search, file search (RAG), code interpreter |
| **03-prompts-eval.ipynb** | ~7 min | Prompt engineering — structured output, few-shot, multi-step reasoning, evaluation |
| **04-orchestration.ipynb** | ~15 min | Multi-agent orchestration — sequential, concurrent, handoff, group chat, RFX workflow |
| **05-byod.ipynb** | ~60 min | Bring your own data — upload documents, build custom agents, multi-agent workflows |
| **e2e-agent-lifecycle.ipynb** | ~30 min | End-to-end agent lifecycle — create, test, trace, evaluate, publish (eastus2 only), monitor |

## Files

```
├── 00-setup.ipynb               # Part 0: Environment setup & Azure infrastructure
├── 01-first-agent.ipynb         # Part 1: First Foundry agent & MCP grounding
├── 02-tools.ipynb               # Part 2: Function, web, file search & code interpreter tools
├── 03-prompts-eval.ipynb        # Part 3: Prompt engineering & evaluation
├── 04-orchestration.ipynb       # Part 4: Multi-agent orchestration patterns
├── 05-byod.ipynb                # Part 5: Bring your own data & custom agents
├── e2e-agent-lifecycle.ipynb    # End-to-end agent lifecycle demo
├── helpdesk_eval_results.json   # Sample evaluation results (IT helpdesk agent)
├── link_checker.py              # URL validation utility (used by RFX workflow)
├── requirements.txt             # Python dependencies
├── infra/
│   ├── main.bicep               # Azure infrastructure template (Bicep)
│   ├── appinsights.bicep        # Additive App Insights template (for pre-provisioned environments)
│   └── main.json                # Compiled ARM template
├── sample_data/
│   ├── eval_dataset.jsonl       # Synthetic evaluation dataset
│   ├── helpdesk_eval_dataset.jsonl          # IT helpdesk evaluation dataset
│   ├── helpdesk_eval_dataset_portal.jsonl   # Helpdesk eval dataset (portal format)
│   ├── it_helpdesk_faq.md       # IT helpdesk knowledge base (FAQ)
│   ├── product_spec.md          # Demo document for file search
│   └── sales_data.csv           # Demo CSV for code interpreter
└── README.md                    # This file
```

## After the Workshop

Your agents are **not deleted** — they remain in your Foundry project. You can:

- Find them in the **Foundry portal → Agents** (sorted by notebook prefix: `01-`, `02-`, `03-`, `04-`, `e2e-`)
- Review traces in **Foundry portal → Tracing**
- View evaluation results in **Foundry portal → Evaluation**
- Continue building by adding tools, data, or deploying as hosted agents

## Optional Cleanup

To delete all Azure resources created during the workshop, run the commented-out
cell at the end of `00-setup.ipynb`, or run:

```bash
az group delete -n <your-resource-group-name> --yes --no-wait
```

## Resources

- [Microsoft Foundry Documentation](https://learn.microsoft.com/azure/ai-foundry/)
- [Foundry Samples](https://github.com/microsoft-foundry/foundry-samples)
- [Agent Framework SDK](https://github.com/microsoft/agent-framework)
- [Azure AI Evaluation](https://learn.microsoft.com/azure/ai-foundry/evaluation/)
