"""Build the Foundry Workshop notebook (foundry_workshop_lab.ipynb)."""
import json, pathlib

cells = []

def md(src: str):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": src.splitlines(True)})

def code(src: str):
    cells.append({"cell_type": "code", "metadata": {}, "outputs": [], "source": src.splitlines(True)})

# ======================================================================
# TITLE
# ======================================================================
md("""# Microsoft Foundry Workshop — Hands-On Lab

Build AI agents from scratch using Microsoft Foundry, covering agent configuration,
tool usage, prompt engineering, multi-step reasoning, evaluation, and multi-agent orchestration.

**This notebook is self-contained** — it deploys all Azure infrastructure, configures tracing,
and walks you through progressively advanced agent patterns.

| Part | Duration | Focus |
|------|----------|-------|
| **Part 1** (Sections 0–5) | ~50 min | Guided baseline — learn all major patterns |
| **Part 2** (Sections 6–9) | ~90 min | Customize with your own data |
""")

# ======================================================================
# SECTION 0: Prerequisites
# ======================================================================
md("""---
## Section 0: Prerequisites & Infrastructure

Before starting, make sure you have:
- **Python 3.10+** installed
- **Azure CLI** (`az`) installed
- An **Azure subscription**
- Run `az login` in your terminal

The cell below validates all prerequisites automatically.
""")

code("""# --- Prerequisite Validation & Helper Setup ---
import subprocess, sys, platform, json, time, os
from pathlib import Path

def run_cmd(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    \"\"\"Run a CLI command (OS-agnostic). Pass args as a list — no shell=True.\"\"\"
    result = subprocess.run(args, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {' '.join(args)}")
        print(f"Error: {result.stderr.strip()}")
        raise RuntimeError(result.stderr.strip())
    return result

print(f"OS:      {platform.system()} {platform.release()}")
print(f"Python:  {sys.version}")
assert sys.version_info >= (3, 10), "Python 3.10+ is required"
print("  ✅ Python version OK")

az_ver = run_cmd(["az", "version"], check=False)
assert az_ver.returncode == 0, "Azure CLI not found — install from https://aka.ms/installazurecli"
print("  ✅ Azure CLI installed")

az_acct = run_cmd(["az", "account", "show"], check=False)
assert az_acct.returncode == 0, "Not logged in — run 'az login' first"
acct = json.loads(az_acct.stdout)
print(f"  ✅ Logged in as: {acct.get('user', {}).get('name', 'unknown')}")
print(f"  ✅ Subscription: {acct.get('name', 'unknown')}")

print("\\n🎉 All prerequisites met!")
""")

# ======================================================================
# SECTION 0A: Deploy Azure Infrastructure
# ======================================================================
md("""### Section 0A: Deploy Azure Infrastructure

The following cells provision all required Azure resources via a **Bicep template**:

| Resource | Purpose |
|----------|---------|
| AI Services account | Foundry host (model access, agent runtime) |
| Foundry Project | Workspace for agents and traces |
| gpt-4.1 deployment | LLM model (80K TPM) |
| Log Analytics + App Insights | Tracing backend |
| RBAC assignments | Permissions for your user |

> ⏱ Deployment takes **3–5 minutes**. You only need to run this once.
""")

code("""# --- Configuration ---
SUFFIX = run_cmd(["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"]).stdout.strip()[:6]

RESOURCE_GROUP = f"rg-foundry-workshop-{SUFFIX}"
LOCATION       = "swedencentral"   # Change if needed (e.g. eastus2, northcentralus)
FOUNDRY_NAME   = f"fndry-ws-{SUFFIX}"
PROJECT_NAME   = "workshop-project"
MODEL_NAME     = "gpt-4.1"
MODEL_VERSION  = "2025-04-14"
MODEL_CAPACITY = 80               # Thousands of tokens per minute

BICEP_PATH = Path.cwd() / "infra" / "main.bicep"

print(f"Resource Group:  {RESOURCE_GROUP}")
print(f"Location:        {LOCATION}")
print(f"Foundry Account: {FOUNDRY_NAME}")
print(f"Project:         {PROJECT_NAME}")
print(f"Model:           {MODEL_NAME} v{MODEL_VERSION}")
print(f"Capacity:        {MODEL_CAPACITY}K TPM")
print(f"Bicep Path:      {BICEP_PATH}")
""")

code("""# --- Create Resource Group ---
print(f"Creating resource group '{RESOURCE_GROUP}' in {LOCATION}...")
result = run_cmd(["az", "group", "create", "-n", RESOURCE_GROUP, "-l", LOCATION, "-o", "table"])
print(result.stdout)
""")

code("""# --- Deploy Bicep Template ---
PRINCIPAL_ID = run_cmd(["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"]).stdout.strip()

print("⏳ Deploying infrastructure (3-5 min)...")
result = run_cmd([
    "az", "deployment", "group", "create",
    "-g", RESOURCE_GROUP,
    "--template-file", str(BICEP_PATH),
    "-p", f"foundryAccountName={FOUNDRY_NAME}",
    "-p", f"projectName={PROJECT_NAME}",
    "-p", f"modelName={MODEL_NAME}",
    "-p", f"modelVersion={MODEL_VERSION}",
    "-p", f"modelCapacity={MODEL_CAPACITY}",
    "-p", f"deployerPrincipalId={PRINCIPAL_ID}",
    "-p", f"location={LOCATION}",
    "-o", "table"
])
print(result.stdout)
print("✅ Infrastructure deployed!")
""")

code("""# --- Parse Deployment Outputs ---
result = run_cmd([
    "az", "deployment", "group", "show",
    "-g", RESOURCE_GROUP, "-n", "main",
    "--query", "properties.outputs", "-o", "json"
])
outputs = json.loads(result.stdout)

PROJECT_ENDPOINT        = outputs["projectEndpoint"]["value"]
MODEL_DEPLOYMENT_NAME   = outputs["modelDeploymentName"]["value"]
APP_INSIGHTS_CONN_STR   = outputs["appInsightsConnectionString"]["value"]
ACCOUNT_NAME            = outputs["accountName"]["value"]
FOUNDRY_RESOURCE_ID     = outputs["foundryResourceId"]["value"]

print(f"Project Endpoint:   {PROJECT_ENDPOINT}")
print(f"Model Deployment:   {MODEL_DEPLOYMENT_NAME}")
print(f"App Insights:       ...{APP_INSIGHTS_CONN_STR[-30:]}")
""")

code("""# --- Create Capability Host (required for Foundry Agents) ---
import requests

SUBSCRIPTION_ID = run_cmd(["az", "account", "show", "--query", "id", "-o", "tsv"]).stdout.strip()
ACCESS_TOKEN = run_cmd([
    "az", "account", "get-access-token",
    "--resource", "https://management.azure.com/",
    "--query", "accessToken", "-o", "tsv"
]).stdout.strip()

headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}

capability_host_url = (
    f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
    f"/resourceGroups/{RESOURCE_GROUP}"
    f"/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT_NAME}"
    f"/capabilityHosts/agents?api-version=2025-10-01-preview"
)

payload = {
    "properties": {
        "capabilityHostKind": "Agents",
        "enablePublicHostingEnvironment": True
    }
}

print("⏳ Creating Capability Host (2-5 min)...")
response = requests.put(capability_host_url, headers=headers, json=payload)
print(f"Initial status: {response.status_code}")

if response.status_code not in (200, 201, 409):
    print(f"Error: {response.text}")
    raise RuntimeError("Capability Host creation failed")

for i in range(36):
    resp = requests.get(capability_host_url, headers=headers)
    if resp.status_code == 200:
        state = resp.json().get("properties", {}).get("provisioningState", "Unknown")
        print(f"  [{i*10}s] {state}")
        if state == "Succeeded":
            print("\\n✅ Capability Host ready!")
            break
        elif state == "Failed":
            print("\\n❌ Capability Host failed")
            print(resp.json())
            break
    time.sleep(10)
else:
    print("\\n⚠️ Timeout — check the Azure portal for status")
""")

md("""### ✅ Infrastructure Ready!

All Azure resources are deployed. You can view your project in the
[Microsoft Foundry Portal](https://ai.azure.com).

**Deployed resources:**
- AI Services account with Foundry project
- gpt-4.1 model deployment (80K TPM)
- Application Insights for tracing
- RBAC roles assigned to your user
- Capability Host for agent runtime
""")

# ======================================================================
# SECTION 0B: Environment Setup & Tracing
# ======================================================================
md("### Section 0B: Environment Setup & Tracing")

code("""# --- Install Python Dependencies ---
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", str(Path.cwd() / "requirements.txt"), "-q"],
    check=True
)
print("✅ Python dependencies installed")
""")

code("""# --- Imports & Authentication ---
import os

# Enable content capture in traces (inputs/outputs visible in Foundry portal)
os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true"

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FileSearchTool, WebSearchPreviewTool
from azure.ai.agents.models import FunctionTool, ToolSet
from azure.identity import DefaultAzureCredential, AzureCliCredential
from opentelemetry import trace

credential = DefaultAzureCredential()

project_client = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=credential,
)
openai_client = project_client.get_openai_client()

print(f"✅ Connected to: {PROJECT_ENDPOINT}")
""")

code("""# --- Configure Tracing ---
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

conn_str = APP_INSIGHTS_CONN_STR
if not conn_str:
    conn_str = project_client.telemetry.get_application_insights_connection_string()

configure_azure_monitor(connection_string=conn_str)
OpenAIInstrumentor().instrument()

tracer = trace.get_tracer("foundry-workshop")

print("✅ Tracing configured — all operations will appear in Foundry portal → Tracing")
print("   (traces may take 1-2 min to appear)")
""")

code("""# --- Verify Connectivity ---
with tracer.start_as_current_span("verify-connectivity"):
    response = openai_client.responses.create(
        model=MODEL_DEPLOYMENT_NAME,
        input="Say 'Hello from Foundry!' in one sentence."
    )
    print(f"🤖 {response.output_text}")
    print("\\n✅ Model is responding. Check Foundry portal → Tracing to see the 'verify-connectivity' span.")
""")

# ======================================================================
# SECTION 1: Your First Foundry Agent
# ======================================================================
md("""---
## Section 1: Your First Foundry Agent (~8 min)

**Foundry Prompt Agents** are server-side agent definitions that combine:
- A **model deployment** (e.g. gpt-4.1)
- **Instructions** (system prompt)
- **Tools** (function calls, web search, file search, etc.)
- **Versioning** — every `create_version()` creates an immutable version

Agents are accessed via the **Responses API** — the same OpenAI-compatible API you know,
but with an `agent_reference` that tells Foundry which agent to use.
""")

code("""# --- Create your first Foundry agent ---
with tracer.start_as_current_span("create-first-agent"):
    first_agent = project_client.agents.create_version(
        agent_name="workshop-assistant",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a helpful workshop assistant. "
                "Answer questions concisely and clearly. "
                "If you don't know something, say so."
            ),
        ),
    )
    print(f"✅ Agent created: {first_agent.name} (version {first_agent.version})")
""")

code("""# --- Chat with your agent via the Responses API ---
with tracer.start_as_current_span("first-agent-chat"):
    response = openai_client.responses.create(
        input="What is Microsoft Foundry and how does it help with AI development?",
        extra_body={
            "agent_reference": {"name": first_agent.name, "type": "agent_reference"}
        },
    )
    print("🧑 What is Microsoft Foundry and how does it help with AI development?\\n")
    print(f"🤖 {response.output_text}")
""")

code("""# --- Multi-turn conversation ---
with tracer.start_as_current_span("multi-turn-conversation"):
    conversation = openai_client.conversations.create()
    print(f"Conversation ID: {conversation.id}\\n")

    # Turn 1
    r1 = openai_client.responses.create(
        input="What are the main components of a Foundry agent?",
        conversation=conversation.id,
        extra_body={"agent_reference": {"name": first_agent.name, "type": "agent_reference"}},
    )
    print("🧑 Turn 1: What are the main components of a Foundry agent?")
    print(f"🤖 {r1.output_text}\\n")

    # Turn 2
    r2 = openai_client.responses.create(
        input="Can you give me a concrete example of the first component?",
        conversation=conversation.id,
        previous_response_id=r1.id,
        extra_body={"agent_reference": {"name": first_agent.name, "type": "agent_reference"}},
    )
    print("🧑 Turn 2: Can you give me a concrete example of the first component?")
    print(f"🤖 {r2.output_text}")
""")

md("""> 💡 **Check it out**: Open the [Foundry Portal](https://ai.azure.com) → your project → **Tracing**.
> You should see spans for `create-first-agent`, `first-agent-chat`, and `multi-turn-conversation`.
""")

# ======================================================================
# SECTION 2: Tool Usage
# ======================================================================
md("""---
## Section 2: Tool Usage (~10 min)

Agents become powerful when you give them **tools**. Foundry supports:

| Tool Type | Description | Use Case |
|-----------|-------------|----------|
| **Function Tool** | Call your Python functions | Database queries, calculations, APIs |
| **Web Search** | Search the web in real-time | Market research, current events |
| **File Search** | Search uploaded documents (RAG) | Internal docs, PDFs, specs |
| **Code Interpreter** | Run Python code | Data analysis, visualizations |
""")

code("""# --- 2.1 Function Tool ---
@tracer.start_as_current_span("get_product_price")
def get_product_price(product_name: str) -> str:
    \"\"\"Look up the list price for a given product.\"\"\"
    prices = {
        "XPR Analytical Balance": "$18,450",
        "T50 Titrator": "$12,000",
        "SevenExcellence pH Meter": "$3,500",
        "DSC 3+ Thermal Analyzer": "$45,000",
    }
    return prices.get(product_name, f"Product '{product_name}' not found in catalog.")

with tracer.start_as_current_span("function-tool-demo"):
    functions = FunctionTool([get_product_price])
    toolset = ToolSet()
    toolset.add(functions)

    pricing_agent = project_client.agents.create_version(
        agent_name="pricing-assistant",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a pricing assistant. Use the get_product_price tool "
                "to look up product prices. Always provide the price in your response."
            ),
            toolset=toolset,
        ),
    )

    thread = project_client.agents.threads.create()
    project_client.agents.messages.create(
        thread_id=thread.id, role="user",
        content="How much does the XPR Analytical Balance cost?"
    )
    run = project_client.agents.runs.create_and_process(
        thread_id=thread.id, agent_id=pricing_agent.id
    )

    if run.status == "failed":
        print(f"❌ Run failed: {run.last_error}")
    else:
        messages = project_client.agents.messages.list(thread_id=thread.id)
        for msg in messages:
            if msg.role == "assistant" and msg.text_messages:
                print("🧑 How much does the XPR Analytical Balance cost?")
                print(f"🤖 {msg.text_messages[-1].text.value}")
                break

    print(f"\\n✅ Function tool agent: {pricing_agent.name} v{pricing_agent.version}")
""")

code("""# --- 2.2 Web Search Tool ---
with tracer.start_as_current_span("web-search-demo"):
    web_agent = project_client.agents.create_version(
        agent_name="web-researcher",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a research assistant. Search the web to find current, "
                "factual information. Always cite your sources with URLs."
            ),
            tools=[WebSearchPreviewTool()],
        ),
    )

    response = openai_client.responses.create(
        input="What are the latest trends in industrial IoT for manufacturing in 2025?",
        extra_body={"agent_reference": {"name": web_agent.name, "type": "agent_reference"}},
    )
    print("🧑 What are the latest trends in industrial IoT for manufacturing in 2025?\\n")
    print(f"🤖 {response.output_text}")
    print(f"\\n✅ Web search agent: {web_agent.name} v{web_agent.version}")
""")

code("""# --- 2.3 File Search Tool ---
with tracer.start_as_current_span("file-search-demo"):
    vector_store = openai_client.vector_stores.create(name="WorkshopDocs")
    spec_path = Path.cwd() / "sample_data" / "product_spec.md"

    with spec_path.open("rb") as f:
        openai_client.vector_stores.files.upload_and_poll(
            vector_store_id=vector_store.id, file=f
        )
    print(f"📄 Uploaded {spec_path.name} to vector store '{vector_store.name}'")

    doc_agent = project_client.agents.create_version(
        agent_name="document-expert",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a product specialist. Use file search to answer questions "
                "about product specifications. Cite specific data from the documents."
            ),
            tools=[FileSearchTool(vector_store_ids=[vector_store.id])],
        ),
    )

    response = openai_client.responses.create(
        input="What is the readability and stabilization time of the XPR balance?",
        extra_body={"agent_reference": {"name": doc_agent.name, "type": "agent_reference"}},
    )
    print(f"\\n🧑 What is the readability and stabilization time of the XPR balance?\\n")
    print(f"🤖 {response.output_text}")
    print(f"\\n✅ File search agent: {doc_agent.name} v{doc_agent.version}")
    print(f"   Vector store ID: {vector_store.id} (keep this — you'll reuse it in Part 2)")
""")

code("""# --- 2.4 Custom CSV Tool ---
import pandas as pd

sales_df = pd.read_csv(Path.cwd() / "sample_data" / "sales_data.csv")
print(f"📊 Loaded sales data: {len(sales_df)} rows\\n")
print(sales_df.head())

@tracer.start_as_current_span("query_sales_data")
def query_sales_data(question: str) -> str:
    \"\"\"Answer questions about sales data. Available columns: product_name, region, quarter, units_sold, revenue_usd.\"\"\"
    summary = sales_df.groupby("product_name").agg(
        total_units=("units_sold", "sum"),
        total_revenue=("revenue_usd", "sum"),
        regions=("region", "nunique"),
    ).reset_index()
    regional = sales_df.groupby(["product_name", "region"]).agg(
        units=("units_sold", "sum"),
        revenue=("revenue_usd", "sum"),
    ).reset_index()
    return f"Product Summary:\\n{summary.to_string(index=False)}\\n\\nRegional Details:\\n{regional.to_string(index=False)}"

with tracer.start_as_current_span("csv-tool-demo"):
    csv_functions = FunctionTool([query_sales_data])
    csv_toolset = ToolSet()
    csv_toolset.add(csv_functions)

    sales_agent = project_client.agents.create_version(
        agent_name="sales-analyst",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a sales data analyst. Use the query_sales_data tool to "
                "answer questions about product sales. Provide specific numbers."
            ),
            toolset=csv_toolset,
        ),
    )

    thread = project_client.agents.threads.create()
    project_client.agents.messages.create(
        thread_id=thread.id, role="user",
        content="Which product has the highest total revenue, and in which region?"
    )
    run = project_client.agents.runs.create_and_process(
        thread_id=thread.id, agent_id=sales_agent.id
    )

    if run.status == "failed":
        print(f"❌ Run failed: {run.last_error}")
    else:
        messages = project_client.agents.messages.list(thread_id=thread.id)
        for msg in messages:
            if msg.role == "assistant" and msg.text_messages:
                print(f"\\n🧑 Which product has the highest total revenue, and in which region?\\n")
                print(f"🤖 {msg.text_messages[-1].text.value}")
                break

    print(f"\\n✅ CSV tool agent: {sales_agent.name} v{sales_agent.version}")
""")

# ======================================================================
# SECTION 3: Prompt Engineering
# ======================================================================
md("""---
## Section 3: Prompt Engineering (~7 min)

The quality of an agent depends heavily on its **instructions** (system prompt).
Key patterns:
- **Persona**: Define who the agent is and its expertise
- **Constraints**: What it should and shouldn't do
- **Output format**: Specify structure (JSON, markdown, etc.)
- **Few-shot examples**: Show desired input/output pairs
""")

code("""# --- 3.1 Basic vs. Engineered Prompt ---
QUESTION = "Analyze the potential of AI in quality control for manufacturing."

with tracer.start_as_current_span("prompt-engineering-comparison"):
    basic_agent = project_client.agents.create_version(
        agent_name="basic-analyst",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions="You are helpful.",
        ),
    )
    r_basic = openai_client.responses.create(
        input=QUESTION,
        extra_body={"agent_reference": {"name": basic_agent.name, "type": "agent_reference"}},
    )

    eng_agent = project_client.agents.create_version(
        agent_name="engineered-analyst",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a senior industrial technology analyst with 15 years of experience "
                "in manufacturing and quality assurance.\\n\\n"
                "RULES:\\n"
                "- Structure your analysis with clear headings\\n"
                "- Include specific, quantifiable benefits where possible\\n"
                "- Address both opportunities AND risks\\n"
                "- Keep responses under 300 words\\n"
                "- End with 3 actionable recommendations\\n\\n"
                "FORMAT: Use markdown with ## headings."
            ),
        ),
    )
    r_eng = openai_client.responses.create(
        input=QUESTION,
        extra_body={"agent_reference": {"name": eng_agent.name, "type": "agent_reference"}},
    )

    print("=" * 60)
    print("BASIC PROMPT RESPONSE:")
    print("=" * 60)
    print(r_basic.output_text[:500])
    print(f"\\n... ({len(r_basic.output_text)} chars total)")
    print("\\n" + "=" * 60)
    print("ENGINEERED PROMPT RESPONSE:")
    print("=" * 60)
    print(r_eng.output_text[:800])
    print(f"\\n... ({len(r_eng.output_text)} chars total)")
""")

code("""# --- 3.2 Structured JSON Output ---
with tracer.start_as_current_span("structured-output-demo"):
    json_agent = project_client.agents.create_version(
        agent_name="structured-analyst",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a business analyst. Always respond with ONLY valid JSON "
                "(no markdown fences, no extra text) using this schema:\\n"
                '{\\n'
                '  "executive_summary": "2-3 sentence overview",\\n'
                '  "key_findings": ["finding 1", "finding 2", "finding 3"],\\n'
                '  "recommendations": ["rec 1", "rec 2"],\\n'
                '  "risk_level": "low | medium | high"\\n'
                '}'
            ),
        ),
    )
    r_json = openai_client.responses.create(
        input="Assess the business case for deploying AI-powered visual inspection in a food processing plant.",
        extra_body={"agent_reference": {"name": json_agent.name, "type": "agent_reference"}},
    )

    print("Raw response:")
    print(r_json.output_text)

    try:
        parsed = json.loads(r_json.output_text)
        print("\\n✅ Valid JSON! Parsed fields:")
        for key, value in parsed.items():
            print(f"  {key}: {value}")
    except json.JSONDecodeError as e:
        print(f"\\n⚠️ JSON parse error: {e}")
""")

code("""# --- 3.3 Few-Shot Prompting ---
with tracer.start_as_current_span("few-shot-demo"):
    fewshot_agent = project_client.agents.create_version(
        agent_name="fewshot-advisor",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a concise technical advisor. Follow the style shown in these examples:\\n\\n"
                "USER: Should we migrate to microservices?\\n"
                "ASSISTANT: **Verdict**: Only if your team exceeds 20 engineers.\\n"
                "**Why**: Microservices add operational overhead (CI/CD, observability, networking). "
                "Below 20 engineers, a modular monolith delivers the same benefits with less complexity.\\n"
                "**Action**: Start with a modular monolith; extract services only when team boundaries demand it.\\n\\n"
                "USER: Is Kubernetes necessary for our 3-service app?\\n"
                "ASSISTANT: **Verdict**: No — use Azure Container Apps instead.\\n"
                "**Why**: K8s is overkill for <10 services. Container Apps provides scale-to-zero, "
                "managed ingress, and Dapr integration without cluster management.\\n"
                "**Action**: Deploy to Container Apps; re-evaluate K8s at 10+ services.\\n\\n"
                "Always use this exact format: **Verdict**, **Why**, **Action**."
            ),
        ),
    )

    r_fs = openai_client.responses.create(
        input="Should we build our own LLM evaluation framework or use an existing one?",
        extra_body={"agent_reference": {"name": fewshot_agent.name, "type": "agent_reference"}},
    )
    print("🧑 Should we build our own LLM evaluation framework or use an existing one?\\n")
    print(f"🤖 {r_fs.output_text}")
""")

# ======================================================================
# SECTION 4: Multi-Step Reasoning & Evaluation
# ======================================================================
md("""---
## Section 4: Multi-Step Reasoning & Evaluation (~10 min)

In this section we'll:
1. Build an agent that performs **multi-step reasoning** (analyze → research → synthesize)
2. **Evaluate** agent quality using Microsoft's built-in evaluators
""")

code("""# --- 4.1 Multi-Step Reasoning Agent ---
with tracer.start_as_current_span("multi-step-reasoning-demo"):
    requirements_agent = project_client.agents.create_version(
        agent_name="requirements-analyst",
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a senior business analyst. When given a vague request, follow these steps:\\n\\n"
                "STEP 1 — ANALYSIS: Identify what's being asked. List assumptions and ambiguities.\\n"
                "STEP 2 — CLARIFYING QUESTIONS: List 3-5 questions you would ask the stakeholder.\\n"
                "STEP 3 — RESEARCH: Based on your knowledge, assess technical feasibility.\\n"
                "STEP 4 — REQUIREMENTS DOCUMENT: Produce a structured output with:\\n"
                "  - Objective (1-2 sentences)\\n"
                "  - Functional Requirements (numbered list)\\n"
                "  - Non-Functional Requirements (numbered list)\\n"
                "  - Risks & Mitigations (table format)\\n"
                "  - Estimated Complexity: Low | Medium | High\\n\\n"
                "Show your reasoning at each step. Use markdown formatting."
            ),
            tools=[WebSearchPreviewTool()],
        ),
    )

    multi_step_query = "We need an AI system that can read our equipment manuals and answer technician questions."

    r_ms = openai_client.responses.create(
        input=multi_step_query,
        extra_body={"agent_reference": {"name": requirements_agent.name, "type": "agent_reference"}},
    )
    print(f"🧑 {multi_step_query}\\n")
    print(f"🤖 {r_ms.output_text}")

    multi_step_response = r_ms.output_text
""")

code("""# --- 4.2 Single-Response Evaluation ---
from azure.ai.evaluation import (
    RelevanceEvaluator,
    CoherenceEvaluator,
    FluencyEvaluator,
)

eval_model_config = {
    "azure_endpoint": PROJECT_ENDPOINT.rsplit("/api/projects", 1)[0],
    "azure_deployment": MODEL_DEPLOYMENT_NAME,
    "api_version": "2025-04-01-preview",
}

relevance = RelevanceEvaluator(eval_model_config)
coherence = CoherenceEvaluator(eval_model_config)
fluency   = FluencyEvaluator(eval_model_config)

print("Evaluating the multi-step reasoning response...\\n")

for name, evaluator in [("Relevance", relevance), ("Coherence", coherence), ("Fluency", fluency)]:
    result = evaluator(
        query=multi_step_query,
        response=multi_step_response,
    )
    score_key = [k for k in result if not k.endswith("_reason") and not k.endswith("_result") and not k.endswith("_threshold")]
    score = result.get(score_key[0], "N/A") if score_key else "N/A"
    reason = result.get(f"{score_key[0]}_reason", "") if score_key else ""
    print(f"  {name}: {score}/5")
    if reason:
        print(f"    Reason: {reason[:120]}...")
    print()
""")

code("""# --- 4.3 Batch Evaluation with Synthetic Dataset ---
from azure.ai.evaluation import evaluate, GroundednessEvaluator

eval_data_path = str(Path.cwd() / "sample_data" / "eval_dataset.jsonl")
groundedness = GroundednessEvaluator(eval_model_config)

print("⏳ Running batch evaluation (this may take 1-2 min)...\\n")

with tracer.start_as_current_span("batch-evaluation-demo"):
    result = evaluate(
        data=eval_data_path,
        evaluators={
            "relevance": relevance,
            "coherence": coherence,
            "fluency": fluency,
            "groundedness": groundedness,
        },
        evaluator_config={
            "groundedness": {
                "column_mapping": {
                    "query": "${data.query}",
                    "context": "${data.context}",
                    "response": "${data.response}",
                }
            }
        },
        azure_ai_project=PROJECT_ENDPOINT,
        output_path=str(Path.cwd() / "eval_results.json"),
    )

    print("=== Aggregate Metrics ===")
    for metric, value in result.get("metrics", {}).items():
        print(f"  {metric}: {value}")

    studio_url = result.get("studio_url", "")
    if studio_url:
        print(f"\\n🔗 View in Foundry Portal: {studio_url}")
    print("\\n✅ Batch evaluation complete!")
""")

md("""> 💡 **Check it out**: Open the [Foundry Portal](https://ai.azure.com) → your project → **Evaluation**
> to see the evaluation results dashboard with per-row scores and aggregate metrics.
""")

# ======================================================================
# SECTION 5: Multi-Agent Orchestration
# ======================================================================
md("""---
## Section 5: Multi-Agent Orchestration (~15 min)

The **Agent Framework SDK** (`agent-framework`) provides orchestration patterns
for coordinating multiple agents. These agents run **in-memory** — ideal for
prototyping complex workflows.

| Pattern | Description | When to use |
|---------|-------------|-------------|
| **Sequential** | Agent A → Agent B → Agent C | Pipelines, staged processing |
| **Concurrent** | All agents run in parallel | Fan-out analysis, multiple perspectives |
| **Handoff** | Router delegates to specialists | Customer support, triage |
| **Group Chat** | Agents discuss collaboratively | Brainstorming, debate, review |

> Agent Framework automatically emits OpenTelemetry spans — visible in Foundry portal → Tracing.
""")

code("""# --- 5.0 Setup Agent Framework ---
import asyncio
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import (
    SequentialBuilder,
    ConcurrentBuilder,
    HandoffBuilder,
    GroupChatBuilder,
)

af_client = FoundryChatClient(
    project_endpoint=PROJECT_ENDPOINT,
    model=MODEL_DEPLOYMENT_NAME,
    credential=AzureCliCredential(),
)

print("✅ Agent Framework client ready")
""")

code("""# --- Define Specialist Agents ---
researcher = Agent(
    client=af_client, name="Researcher",
    instructions=(
        "You are a thorough researcher. Gather key facts, data points, "
        "and insights on the given topic. Be specific and cite numbers when possible. "
        "Keep your research summary under 200 words."
    ),
)

writer = Agent(
    client=af_client, name="Writer",
    instructions=(
        "You are a professional writer. Transform research notes or raw input "
        "into polished, well-structured documents. Use clear headings, concise "
        "paragraphs, and professional tone. Keep output under 300 words."
    ),
)

critic = Agent(
    client=af_client, name="Critic",
    instructions=(
        "You are a constructive critic. Review the content for accuracy, "
        "completeness, clarity, and persuasiveness. Provide 3-5 specific, "
        "actionable improvement suggestions. Be direct but respectful."
    ),
)

customer_support = Agent(
    client=af_client, name="CustomerSupport",
    instructions=(
        "You handle customer service inquiries. Be empathetic, provide "
        "clear solutions, and confirm the customer's issue is resolved. "
        "If you can't resolve it, explain next steps."
    ),
)

travel_planner = Agent(
    client=af_client, name="TravelPlanner",
    instructions=(
        "You create detailed travel itineraries. Include flights, "
        "accommodation, key activities, estimated costs, and practical "
        "tips. Format as a day-by-day plan."
    ),
)

budget_analyst = Agent(
    client=af_client, name="BudgetAnalyst",
    instructions=(
        "You analyze budgets and costs. Break down expenses, identify "
        "savings opportunities, and provide financial recommendations. "
        "Always include a summary table."
    ),
)

print("✅ 6 specialist agents defined: Researcher, Writer, Critic, CustomerSupport, TravelPlanner, BudgetAnalyst")
""")

code("""# --- 5.1 Sequential Orchestration ---
print("=" * 60)
print("SEQUENTIAL: Researcher → Writer")
print("=" * 60)

seq_workflow = SequentialBuilder(participants=[researcher, writer]).build()

async def run_sequential():
    async for event in seq_workflow.run(
        "Write a market analysis report on the electric vehicle industry in Europe.",
        stream=True
    ):
        if event.type == "output":
            for msg in event.data:
                print(f"\\n[{msg.author_name}]:")
                print(msg.text[:500])

await run_sequential()
print("\\n✅ Sequential orchestration complete")
""")

code("""# --- 5.2 Concurrent Orchestration ---
print("=" * 60)
print("CONCURRENT: Researcher + Writer + Critic (parallel)")
print("=" * 60)

conc_workflow = ConcurrentBuilder(participants=[researcher, writer, critic]).build()

async def run_concurrent():
    result = await conc_workflow.run(
        "Analyze the pros and cons of implementing a 4-day work week in a tech company."
    )
    outputs = result.get_outputs()
    for output in outputs:
        for msg in output:
            print(f"\\n[{msg.author_name}]:")
            print(msg.text[:400])
            print("---")

await run_concurrent()
print("\\n✅ Concurrent orchestration complete")
""")

code("""# --- 5.3 Handoff Orchestration ---
print("=" * 60)
print("HANDOFF: Triage → Specialists")
print("=" * 60)

triage = Agent(
    client=af_client, name="Triage",
    instructions=(
        "You are a customer service triage agent. Analyze the user's request "
        "and route to the most appropriate specialist:\\n"
        "- CustomerSupport: complaints, returns, account issues\\n"
        "- TravelPlanner: travel planning, itineraries, trip advice\\n"
        "- BudgetAnalyst: cost analysis, budget planning, financial questions\\n\\n"
        "Transfer to the right specialist with a brief context summary."
    ),
)

for a in [triage, customer_support, travel_planner, budget_analyst]:
    a.require_per_service_call_history_persistence = True

handoff_workflow = (
    HandoffBuilder(
        name="customer_routing",
        participants=[triage, customer_support, travel_planner, budget_analyst],
    )
    .with_start_agent(triage)
    .add_handoff(triage, [customer_support, travel_planner, budget_analyst])
    .add_handoff(customer_support, [triage])
    .add_handoff(travel_planner, [triage])
    .add_handoff(budget_analyst, [triage])
    .build()
)

async def run_handoff():
    async for event in handoff_workflow.run(
        "I need to plan a business trip to Tokyo next month within a $5,000 budget. "
        "Can you help me with the itinerary and cost breakdown?",
        stream=True
    ):
        if event.type == "output":
            for msg in event.data:
                print(f"\\n[{msg.author_name}]:")
                print(msg.text[:500])

await run_handoff()
print("\\n✅ Handoff orchestration complete")
""")

code("""# --- 5.4 Group Chat Orchestration ---
print("=" * 60)
print("GROUP CHAT: Orchestrator + Researcher + Writer + Critic")
print("=" * 60)

orchestrator = Agent(
    client=af_client, name="Orchestrator",
    description="Coordinates multi-agent collaboration by selecting speakers",
    instructions=(
        "You coordinate a team discussion. Select the best next speaker based on "
        "what's needed: Researcher for facts, Writer for drafting, Critic for review. "
        "Aim for a productive 3-round discussion."
    ),
)

gc_workflow = (
    GroupChatBuilder(
        participants=[researcher, writer, critic],
        orchestrator_agent=orchestrator,
        termination_condition=lambda msgs: sum(1 for m in msgs if m.role == "assistant") >= 4,
        max_rounds=6,
        intermediate_outputs=True,
    )
    .build()
)

async def run_group_chat():
    async for event in gc_workflow.run(
        "Create a compelling product launch announcement for a new AI-powered "
        "customer service platform that reduces response time by 80%.",
        stream=True
    ):
        if event.type == "output":
            if isinstance(event.data, list):
                for msg in event.data:
                    print(f"\\n[{msg.author_name}]:")
                    print(msg.text[:400])
                    print("---")
            else:
                print(f"\\n[{getattr(event.data, 'author_name', 'Agent')}]:")
                text = getattr(event.data, 'text', str(event.data))
                print(text[:400])

await run_group_chat()
print("\\n✅ Group chat orchestration complete")
""")

md("""> 💡 **Check the traces**: Open **Foundry Portal → Tracing**. You'll see `workflow.session`,
> `executor.process`, and `message.send` spans showing exactly how the agents collaborated.

---
""")

# ======================================================================
# PART 2: Bring Your Own Data
# ======================================================================
md("""# Part 2: Bring Your Own Data (90 min)

Now it's your turn! Use the patterns from Part 1 to build agents with **your own data**.

---
## Section 6: Upload Your Own Data (~20 min)

### Supported file types for `file_search`:
PDF, DOCX, TXT, MD, PPTX, JSON, HTML — CSV is **not** supported, use a function tool instead.

### Steps:
1. Place your files in a folder (or use `sample_data/`)
2. Run the upload helper below
3. The vector store ID will be used to create your agent
""")

code("""# --- File Upload Helper ---
def upload_files_to_vector_store(file_paths: list, store_name: str = "MyData") -> str:
    \"\"\"Upload files to a vector store and return the store ID.\"\"\"
    with tracer.start_as_current_span("upload-own-data"):
        vs = openai_client.vector_stores.create(name=store_name)
        print(f"📦 Created vector store: {store_name} (ID: {vs.id})")

        for fp in file_paths:
            p = Path(fp)
            if not p.exists():
                print(f"  ⚠️ File not found: {p}")
                continue
            with p.open("rb") as f:
                openai_client.vector_stores.files.upload_and_poll(
                    vector_store_id=vs.id, file=f
                )
            print(f"  ✅ Uploaded: {p.name}")

        print(f"\\n📦 Vector store ready: {vs.id}")
        return vs.id

print("Helper function defined. Use it in the next cell.")
""")

code("""# --- CSV / Excel Helper ---
def load_dataframe(path: str) -> pd.DataFrame:
    \"\"\"Load a CSV or Excel file into a pandas DataFrame.\"\"\"
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    elif p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p)
    else:
        raise ValueError(f"Unsupported format: {p.suffix}")

user_dataframes = {}

@tracer.start_as_current_span("query_user_data")
def query_user_data(dataset_name: str, question: str) -> str:
    \"\"\"Query a loaded dataset. Provide the dataset name and your question.\"\"\"
    if dataset_name not in user_dataframes:
        return f"Dataset '{dataset_name}' not loaded. Available: {list(user_dataframes.keys())}"
    df = user_dataframes[dataset_name]
    summary = df.describe(include="all").to_string()
    sample = df.head(5).to_string()
    return f"Columns: {list(df.columns)}\\nShape: {df.shape}\\n\\nSummary:\\n{summary}\\n\\nSample rows:\\n{sample}"

print("CSV/Excel helper ready. Load your files with:")
print('  user_dataframes["mydata"] = load_dataframe("path/to/file.csv")')
""")

code("""# ============================================================
# TODO: Upload your files here!
# ============================================================

# Option 1: Upload documents (PDF, DOCX, MD, TXT, PPTX, JSON)
# my_files = [
#     "path/to/your/document.pdf",
#     "path/to/your/report.docx",
# ]
# MY_VECTOR_STORE_ID = upload_files_to_vector_store(my_files, "MyProjectDocs")

# Option 2: Load CSV/Excel data
# user_dataframes["sales"] = load_dataframe("path/to/data.csv")
# print(user_dataframes["sales"].head())

# --- Example using the sample data (uncomment to try) ---
# MY_VECTOR_STORE_ID = upload_files_to_vector_store(
#     [str(Path.cwd() / "sample_data" / "product_spec.md")],
#     "SampleDocs"
# )
# user_dataframes["sales"] = load_dataframe(str(Path.cwd() / "sample_data" / "sales_data.csv"))

print("👆 Uncomment and modify the code above to upload your files.")
""")

# ======================================================================
# SECTION 7: Build Your Custom Agent
# ======================================================================
md("""---
## Section 7: Build Your Custom Agent (~25 min)

Use what you learned in Sections 1–4 to create an agent tailored to **your data**.

**Tips from Section 3:**
- Define a clear **persona** and **expertise area**
- Set **constraints** (what it should/shouldn't do)
- Specify **output format** (JSON, markdown, bullet points)
- Add **few-shot examples** if you want a specific style
""")

code("""# ============================================================
# TODO: Build your custom agent!
# ============================================================

with tracer.start_as_current_span("custom-agent-creation"):

    # TODO: Choose your agent name
    MY_AGENT_NAME = "my-custom-agent"  # e.g. "rfp-assistant", "data-analyst"

    # TODO: Write your instructions (use the patterns from Section 3)
    MY_INSTRUCTIONS = (
        "You are a helpful assistant. "  # <-- Replace with your persona and rules
        "Answer questions based on the provided documents."
    )

    # TODO: Choose your tools
    my_tools = []
    # Uncomment the tools you want:
    # my_tools.append(FileSearchTool(vector_store_ids=[MY_VECTOR_STORE_ID]))  # Document search
    # my_tools.append(WebSearchPreviewTool())  # Web search

    # If using CSV data, add the function tool:
    # csv_tool = FunctionTool([query_user_data])
    # csv_ts = ToolSet()
    # csv_ts.add(csv_tool)
    # (pass toolset=csv_ts to create_version instead of tools=my_tools)

    my_agent = project_client.agents.create_version(
        agent_name=MY_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=MY_INSTRUCTIONS,
            tools=my_tools if my_tools else None,
        ),
    )

    print(f"✅ Custom agent created: {my_agent.name} v{my_agent.version}")
""")

code("""# --- Test Your Agent ---

# TODO: Replace these with questions relevant to YOUR data
test_questions = [
    "What is the main topic of the uploaded documents?",
    "Summarize the key findings.",
    "What are the top 3 recommendations?",
]

with tracer.start_as_current_span("custom-agent-test"):
    for i, q in enumerate(test_questions, 1):
        print(f"\\n{'=' * 50}")
        print(f"Test {i}: {q}")
        print("=" * 50)

        response = openai_client.responses.create(
            input=q,
            extra_body={"agent_reference": {"name": my_agent.name, "type": "agent_reference"}},
        )
        print(f"🤖 {response.output_text[:500]}")
""")

# ======================================================================
# SECTION 8: Build Your Multi-Agent Workflow
# ======================================================================
md("""---
## Section 8: Build Your Multi-Agent Workflow (~30 min)

Combine multiple agents into a workflow. Choose the pattern that fits your use case:

| Your Goal | Pattern | Example |
|-----------|---------|---------|
| Step-by-step processing | **Sequential** | Research → Draft → Review |
| Multiple perspectives at once | **Concurrent** | Legal + Technical + Business analysis |
| Route to the right expert | **Handoff** | Triage → Specialist agents |
| Collaborative discussion | **Group Chat** | Team of agents refining an answer |
""")

code("""# ============================================================
# TODO: Define your specialist agents
# ============================================================

agent_1 = Agent(
    client=af_client, name="Agent1",
    instructions="TODO: Define this agent's role and expertise.",
)

agent_2 = Agent(
    client=af_client, name="Agent2",
    instructions="TODO: Define this agent's role and expertise.",
)

# Optional third agent:
# agent_3 = Agent(
#     client=af_client, name="Agent3",
#     instructions="TODO: Define this agent's role and expertise.",
# )

print("Specialist agents defined. Choose your orchestration pattern in the next cell.")
""")

code("""# ============================================================
# TODO: Choose your orchestration pattern
# Uncomment ONE of the blocks below.
# ============================================================

MY_TASK = "TODO: Describe the task for your agents"  # <-- Change this!

# --- Option A: Sequential ---
# workflow = SequentialBuilder(participants=[agent_1, agent_2]).build()

# --- Option B: Concurrent ---
# workflow = ConcurrentBuilder(participants=[agent_1, agent_2]).build()

# --- Option C: Handoff ---
# for a in [agent_1, agent_2]:
#     a.require_per_service_call_history_persistence = True
# router = Agent(
#     client=af_client, name="Router",
#     instructions="Route to the right specialist based on the request.",
# )
# router.require_per_service_call_history_persistence = True
# workflow = (
#     HandoffBuilder(name="my-workflow", participants=[router, agent_1, agent_2])
#     .with_start_agent(router)
#     .add_handoff(router, [agent_1, agent_2])
#     .add_handoff(agent_1, [router])
#     .add_handoff(agent_2, [router])
#     .build()
# )

# --- Option D: Group Chat ---
# orch = Agent(
#     client=af_client, name="Orchestrator",
#     instructions="Coordinate the discussion between agents.",
# )
# workflow = (
#     GroupChatBuilder(
#         participants=[agent_1, agent_2],
#         orchestrator_agent=orch,
#         max_rounds=6,
#     ).build()
# )

print("👆 Uncomment your chosen pattern above, then run the next cell.")
""")

code("""# --- Run Your Workflow ---

async def run_my_workflow():
    with tracer.start_as_current_span("custom-workflow"):
        async for event in workflow.run(MY_TASK, stream=True):
            if event.type == "output":
                data = event.data if isinstance(event.data, list) else [event.data]
                for msg in data:
                    name = getattr(msg, 'author_name', 'Agent')
                    text = getattr(msg, 'text', str(msg))
                    print(f"\\n[{name}]:")
                    print(text[:500])
                    print("---")

await run_my_workflow()
print("\\n✅ Custom workflow complete! Check Foundry portal → Tracing for the workflow spans.")
""")

# ======================================================================
# SECTION 9: Wrap-Up
# ======================================================================
md("""---
## Section 9: Wrap-Up & Next Steps

### 🎉 Congratulations!

You've built and tested:
- ✅ Single agents with function tools, web search, and file search
- ✅ Prompt-engineered agents with structured output
- ✅ Multi-step reasoning agents
- ✅ Agent quality evaluation with built-in evaluators
- ✅ Multi-agent workflows (sequential, concurrent, handoff, group chat)
- ✅ Custom agents with your own data

### 🚀 Your agents are still live!

All agents you created during this workshop are **still available** in your Foundry project.
You can continue building on them:

| Agent | Type | How to find it |
|-------|------|----------------|
| workshop-assistant | Prompt Agent | Foundry Portal → Agents |
| pricing-assistant | Function Tool Agent | Foundry Portal → Agents |
| web-researcher | Web Search Agent | Foundry Portal → Agents |
| document-expert | File Search Agent | Foundry Portal → Agents |
| sales-analyst | CSV Tool Agent | Foundry Portal → Agents |
| requirements-analyst | Multi-Step Agent | Foundry Portal → Agents |
| Your custom agent(s) | Custom | Foundry Portal → Agents |

### 📊 Review Your Traces & Evaluation

- **Traces**: [Foundry Portal](https://ai.azure.com) → your project → **Tracing**
- **Evaluation**: [Foundry Portal](https://ai.azure.com) → your project → **Evaluation**

### 📚 Next Steps

| Topic | Resource |
|-------|----------|
| Deploy as hosted agent | [Hosted Agents docs](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/hosted-agents) |
| Production RAG with AI Search | [AI Search tool](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/tools/ai-search) |
| Governance & monitoring | [Enterprise Agent Tutorial](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/enterprise-agent-tutorial) |
| Agent Framework SDK | [GitHub repo](https://github.com/microsoft/agent-framework) |
| Evaluation best practices | [Azure AI Evaluation](https://learn.microsoft.com/azure/ai-foundry/evaluation/) |
""")

code("""# ============================================================
# OPTIONAL: Resource Cleanup
# ============================================================
# Uncomment the lines below to delete ALL Azure resources
# created during this workshop. This is irreversible!

# print(f"⚠️  Deleting resource group: {RESOURCE_GROUP}")
# run_cmd(["az", "group", "delete", "-n", RESOURCE_GROUP, "--yes", "--no-wait"])
# print("✅ Deletion initiated (will complete in background)")

print("No cleanup performed — your agents and resources are still available.")
print(f"Resource group: {RESOURCE_GROUP}")
print(f"Project endpoint: {PROJECT_ENDPOINT}")
""")

# ======================================================================
# Write notebook
# ======================================================================
nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "codemirror_mode": {"name": "ipython", "version": 3},
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "nbconvert_exporter": "python",
            "pygments_lexer": "ipython3",
            "version": "3.12.0"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = pathlib.Path(__file__).parent / "foundry_workshop_lab.ipynb"
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")

# Summary
md_count = sum(1 for c in cells if c["cell_type"] == "markdown")
code_count = sum(1 for c in cells if c["cell_type"] == "code")
full_src = "".join("".join(c["source"]) for c in cells)

print(f"✅ Notebook written to: {out}")
print(f"   Total cells:  {len(cells)}")
print(f"   Markdown:     {md_count}")
print(f"   Code:         {code_count}")
print(f"   Total chars:  {len(full_src):,}")

issues = []
# Check for actual shell=True usage (not in comments/docstrings)
code_src = "".join("".join(c["source"]) for c in cells if c["cell_type"] == "code")
if "shell=True" in code_src.replace("no shell=True", ""):
    issues.append("Found 'shell=True'")
if "delete_agent" in code_src or "delete_version" in code_src:
    issues.append("Found agent deletion code")
if issues:
    for iss in issues:
        print(f"   ⚠️ {iss}")
else:
    print("   ✅ No OS-specific or cleanup issues")
