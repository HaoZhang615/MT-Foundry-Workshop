"""
Fan-out / Fan-in workflow test (adapted from official sample).
A dispatcher fans out to 3 expert agents in parallel,
then an aggregator joins their responses into a consolidated report.
"""

import asyncio
import subprocess
import json
from dataclasses import dataclass

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponseUpdate,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.devui import serve
from azure.identity import AzureCliCredential
from typing_extensions import Never


# --- Auto-detect Foundry project endpoint ---
def get_project_config():
    suffix = subprocess.run(
        ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"],
        capture_output=True, text=True,
    ).stdout.strip()[:6]
    rg = f"rg-foundry-workshop-{suffix}"
    outputs = json.loads(subprocess.run(
        ["az", "deployment", "group", "show", "-g", rg, "-n", "main",
         "--query", "properties.outputs", "-o", "json"],
        capture_output=True, text=True,
    ).stdout)
    return outputs["projectEndpoint"]["value"], outputs["modelDeploymentName"]["value"]


PROJECT_ENDPOINT, MODEL = get_project_config()
print(f"Using project: {PROJECT_ENDPOINT}")
print(f"Using model: {MODEL}")


# --- Custom Executors ---

class DispatchToExperts(Executor):
    """Fans out the incoming prompt to all expert agents in parallel."""

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        initial_message = Message("user", contents=[prompt])
        await ctx.send_message(AgentExecutorRequest(messages=[initial_message], should_respond=True))


@dataclass
class AggregatedInsights:
    research: str
    marketing: str
    legal: str


class AggregateInsights(Executor):
    """Joins expert responses into a single consolidated report."""

    @handler
    async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
        by_id: dict[str, str] = {}
        for r in results:
            by_id[r.executor_id] = r.agent_response.text

        research_text = by_id.get("researcher", "")
        marketing_text = by_id.get("marketer", "")
        legal_text = by_id.get("legal", "")

        consolidated = (
            f"Consolidated Insights\n{'=' * 40}\n\n"
            f"Research Findings:\n{research_text}\n\n"
            f"Marketing Angle:\n{marketing_text}\n\n"
            f"Legal/Compliance Notes:\n{legal_text}\n"
        )
        await ctx.yield_output(consolidated)


# --- Build entities ---

credential = AzureCliCredential()
client = FoundryChatClient(project_endpoint=PROJECT_ENDPOINT, model=MODEL, credential=credential)

dispatcher = DispatchToExperts(id="dispatcher")
aggregator = AggregateInsights(id="aggregator")

researcher = AgentExecutor(
    Agent(
        client=client,
        instructions=(
            "You're an expert market and product researcher. Given a prompt, "
            "provide concise, factual insights, opportunities, and risks."
        ),
        name="researcher",
    )
)

marketer = AgentExecutor(
    Agent(
        client=client,
        instructions=(
            "You're a creative marketing strategist. Craft compelling value "
            "propositions and target messaging aligned to the prompt."
        ),
        name="marketer",
    )
)

legal = AgentExecutor(
    Agent(
        client=client,
        instructions=(
            "You're a cautious legal/compliance reviewer. Highlight constraints, "
            "disclaimers, and policy concerns based on the prompt."
        ),
        name="legal",
    )
)

# Build fan-out / fan-in workflow
workflow = (
    WorkflowBuilder(name="Fan-Out Fan-In Analysis", start_executor=dispatcher)
    .add_fan_out_edges(dispatcher, [researcher, marketer, legal])
    .add_fan_in_edges([researcher, marketer, legal], aggregator)
    .build()
)

print("\nStarting DevUI on http://localhost:8090")
print("Entities: dispatcher → [researcher, marketer, legal] → aggregator")
serve(entities=[workflow], port=8090, auto_open=False, instrumentation_enabled=True)
