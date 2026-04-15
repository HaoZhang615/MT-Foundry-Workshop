# Microsoft Foundry Workshop — Hands-On Lab

## Overview

This hands-on lab walks you through building AI agents using Microsoft Foundry,
from infrastructure deployment to multi-agent orchestration. The notebook is
self-contained: it provisions all Azure resources, configures tracing, and
guides you through progressively advanced agent patterns.

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

> The notebook validates all prerequisites automatically in its first cells.

## Quick Start

1. **Clone or download** this folder to your local machine.
2. **Open** the folder in VS Code.
3. **Open** `foundry_workshop_lab.ipynb`.
4. **Run the first code cell** — it creates a `.venv` and installs all dependencies using `uv`.
5. **Select the `.venv` kernel** — click "Select Kernel" in the top-right, choose "Python Environments…", and pick `.venv`.
6. **Run cells sequentially** — the notebook will:
   - Validate prerequisites
   - Deploy all Azure infrastructure (AI Services, model, App Insights)
   - Walk you through agent development

## Workshop Structure

| Section | Duration | Topics |
|---------|----------|--------|
| **Section 0** | ~10 min | Prerequisites, Azure infrastructure deployment, tracing setup |
| **Section 1** | ~8 min | Your first Foundry agent — create, chat, multi-turn |
| **Section 2** | ~10 min | Tool usage — function tools, web search, file search, CSV |
| **Section 3** | ~7 min | Prompt engineering — structured output, few-shot |
| **Section 4** | ~10 min | Multi-step reasoning and evaluation |
| **Section 5** | ~15 min | Multi-agent orchestration — sequential, concurrent, handoff, group chat |
| **Section 6** | ~20 min | Upload your own data |
| **Section 7** | ~25 min | Build your custom agent |
| **Section 8** | ~30 min | Build your multi-agent workflow |
| **Section 9** | ~15 min | Wrap-up and next steps |

## Files

```
├── foundry_workshop_lab.ipynb   # Main workshop notebook
├── requirements.txt             # Python dependencies
├── infra/
│   └── main.bicep               # Azure infrastructure template
├── sample_data/
│   ├── product_spec.md          # Demo document for file search
│   ├── sales_data.csv           # Demo CSV for function tools
│   └── eval_dataset.jsonl       # Synthetic evaluation dataset
└── README.md                    # This file
```

## After the Workshop

Your agents are **not deleted** — they remain in your Foundry project. You can:

- Find them in the **Foundry portal → Agents**
- Review traces in **Foundry portal → Tracing**
- View evaluation results in **Foundry portal → Evaluation**
- Continue building by adding tools, data, or deploying as hosted agents

## Optional Cleanup

To delete all Azure resources created during the workshop, run the commented-out
cell at the end of the notebook, or run:

```bash
az group delete -n <your-resource-group-name> --yes --no-wait
```

## Resources

- [Microsoft Foundry Documentation](https://learn.microsoft.com/azure/ai-foundry/)
- [Foundry Samples](https://github.com/microsoft-foundry/foundry-samples)
- [Agent Framework SDK](https://github.com/microsoft/agent-framework)
- [Azure AI Evaluation](https://learn.microsoft.com/azure/ai-foundry/evaluation/)
