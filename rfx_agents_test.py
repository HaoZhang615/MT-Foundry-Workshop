"""
RFX Multi-Agent QA Workflow — Agent Framework + DevUI.

Topology (visible as graph in DevUI):

  QuestionAnswerer (MCP) → dispatcher → fan-out → [AnswerChecker (WebSearch), LinkChecker (function tool)]
                                                          ↓                            ↓
                                                   fan-in → collector → manager
                                                                          ↓
                                                         switch-case: APPROVE → output
                                                                       reject → QuestionAnswerer (loop)

Run:  python rfx_agents_test.py
DevUI: http://localhost:8090
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
    Case,
    Default,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.foundry import FoundryChatClient, FoundryAgent
from agent_framework.devui import serve
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition, WebSearchPreviewTool
from azure.identity import AzureCliCredential
from typing_extensions import Never

from link_checker import validate_urls_in_text


# ============================================================
# Project config
# ============================================================

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

credential = AzureCliCredential()
client = FoundryChatClient(
    project_endpoint=PROJECT_ENDPOINT,
    model=MODEL,
    credential=credential,
)
project_client = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)


# ============================================================
# Agent definitions
# ============================================================

# 1) QuestionAnswerer — FoundryAgent with MCP (Microsoft Learn docs)
qa_prompt = project_client.agents.create_version(
    agent_name="rfx-question-answerer",
    definition=PromptAgentDefinition(
        model=MODEL,
        instructions=(
            "You are a question answerer for Microsoft technologies to help with RFP/RFQ/RFI situations. "
            "You take questions and provide detailed, accurate answers from the perspective of "
            "Microsoft Azure, AI, and cloud services.\n\n"
            "RULES:\n"
            "- ALWAYS use the MCP tool to search Microsoft Learn documentation before answering\n"
            "- Provide factual answers with concrete details (features, certifications, SLAs)\n"
            "- Include relevant Microsoft Learn documentation links from the MCP search results\n"
            "- If you don't know something, say so — don't fabricate information\n"
            "- Keep answers professional and suitable for enterprise procurement\n"
            "- If you receive feedback from checkers, fix ONLY those specific issues\n"
            "- Keep your answer under 400 words"
        ),
        tools=[
            MCPTool(
                server_label="microsoft-learn",
                server_url="https://learn.microsoft.com/api/mcp",
                require_approval="never",
            ),
        ],
    ),
)
print(f"✅ Foundry agent: {qa_prompt.name} v{qa_prompt.version}")

question_answerer = FoundryAgent(
    project_endpoint=PROJECT_ENDPOINT,
    agent_name=qa_prompt.name,
    agent_version=qa_prompt.version,
    credential=credential,
    name="QuestionAnswerer",
)

# 2) AnswerChecker — FoundryAgent with WebSearch
checker_prompt = project_client.agents.create_version(
    agent_name="rfx-answer-checker",
    definition=PromptAgentDefinition(
        model=MODEL,
        instructions=(
            "You are a QA checker for RFP/RFI responses about Microsoft technologies.\n\n"
            "VERIFICATION PROCESS:\n"
            "1. Use web search to independently verify key claims in the answer\n"
            "2. Check factual accuracy against your search results\n"
            "3. Check completeness — does the answer fully address the question?\n"
            "4. Check tone — professional and suitable for enterprise procurement?\n\n"
            "RESPONSE FORMAT:\n"
            "- If everything checks out, respond with ONLY: ANSWER CORRECT\n"
            "  Do NOT add verification notes, explanations, or details when correct.\n"
            "- If issues found, start with 'ANSWER INCORRECT' then list each issue\n"
            "- Do NOT rewrite the answer — just identify the issues"
        ),
        tools=[WebSearchPreviewTool()],
    ),
)
print(f"✅ Foundry agent: {checker_prompt.name} v{checker_prompt.version}")

answer_checker = FoundryAgent(
    project_endpoint=PROJECT_ENDPOINT,
    agent_name=checker_prompt.name,
    agent_version=checker_prompt.version,
    credential=credential,
    name="AnswerChecker",
)

# 3) LinkChecker — in-memory Agent with validate_urls function tool
link_checker = Agent(
    client=client,
    name="LinkChecker",
    description="Validates all URLs in the answer by making HTTP requests",
    instructions=(
        "You are a link checker. Your ONLY job is to validate URLs.\n\n"
        "PROCESS:\n"
        "1. Call validate_urls_in_text with the FULL text you received\n"
        "2. Return the function result EXACTLY as-is\n\n"
        "If the text has no URLs, respond with: LINKS CORRECT\n"
        "Do NOT make your own assessment — rely ONLY on the function results."
    ),
    tools=[validate_urls_in_text],
)


# ============================================================
# Custom Executors for the workflow graph
# ============================================================

class InputReceiver(Executor):
    """Accepts plain text input and converts it to an AgentExecutorRequest for the QA agent."""

    @handler
    async def receive(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        msg = Message("user", contents=[prompt])
        await ctx.send_message(AgentExecutorRequest(messages=[msg], should_respond=True))


class DispatchToCheckers(Executor):
    """Takes the QA agent's response and fans it out to both checkers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_answer = ""  # Store QA answer for the collector

    @handler
    async def dispatch(self, response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        self.last_answer = response.agent_response.text
        msg = Message("user", contents=[self.last_answer])
        await ctx.send_message(AgentExecutorRequest(messages=[msg], should_respond=True))


@dataclass
class CheckerVerdict:
    """Structured result from both checkers."""
    qa_answer: str
    answer_check: str
    link_check: str


class CollectCheckerResults(Executor):
    """Fans in results from AnswerChecker and LinkChecker into a single verdict."""

    def __init__(self, dispatcher_ref: DispatchToCheckers, **kwargs):
        super().__init__(**kwargs)
        self._dispatcher = dispatcher_ref

    @handler
    async def collect(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[CheckerVerdict]) -> None:
        by_id: dict[str, str] = {}
        for r in results:
            by_id[r.executor_id] = r.agent_response.text

        verdict = CheckerVerdict(
            qa_answer=self._dispatcher.last_answer,
            answer_check=by_id.get("AnswerChecker", ""),
            link_check=by_id.get("LinkChecker", ""),
        )
        await ctx.send_message(verdict)


@dataclass
class ManagerDecision:
    """Output from the manager: approved answer or rejection feedback."""
    approved: bool
    content: str  # final answer if approved, feedback if rejected


class ManagerExecutor(Executor):
    """Evaluates checker results: approve or reject with feedback."""

    @handler
    async def decide(self, verdict: CheckerVerdict, ctx: WorkflowContext[ManagerDecision]) -> None:
        answer_ok = verdict.answer_check.strip().upper().startswith("ANSWER CORRECT")
        links_ok = not verdict.link_check.strip().upper().startswith("LINKS INCORRECT")

        if answer_ok and links_ok:
            decision = ManagerDecision(approved=True, content=verdict.qa_answer)
        else:
            feedback_parts = []
            if not answer_ok:
                feedback_parts.append(f"AnswerChecker feedback:\n{verdict.answer_check}")
            if not links_ok:
                feedback_parts.append(f"LinkChecker feedback:\n{verdict.link_check}")
            feedback = (
                "Your previous answer was REJECTED. Please fix these issues and resubmit:\n\n"
                + "\n\n".join(feedback_parts)
            )
            decision = ManagerDecision(approved=False, content=feedback)

        await ctx.send_message(decision)


class FeedbackToQA(Executor):
    """Converts rejection feedback into an AgentExecutorRequest for the QA agent."""

    @handler
    async def send_feedback(self, decision: ManagerDecision, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        msg = Message("user", contents=[decision.content])
        await ctx.send_message(AgentExecutorRequest(messages=[msg], should_respond=True))


class ApprovedOutput(Executor):
    """Emits the final approved answer as workflow output."""

    @handler
    async def emit(self, decision: ManagerDecision, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(decision.content)


# ============================================================
# Build the workflow
# ============================================================

# Executor instances
input_recv = InputReceiver(id="input")
dispatcher = DispatchToCheckers(id="dispatcher")
collector = CollectCheckerResults(dispatcher_ref=dispatcher, id="collector")
manager_exec = ManagerExecutor(id="manager")
feedback_exec = FeedbackToQA(id="feedback")
output_exec = ApprovedOutput(id="output")

workflow = (
    WorkflowBuilder(
        name="RFX Quality Assurance",
        start_executor=input_recv,
        max_iterations=10,
    )
    # input → QA agent
    .add_edge(input_recv, question_answerer)
    # QA → dispatcher (extracts answer text)
    .add_edge(question_answerer, dispatcher)
    # dispatcher → fan-out to both checkers in parallel
    .add_fan_out_edges(dispatcher, [answer_checker, link_checker])
    # both checkers → fan-in to collector
    .add_fan_in_edges([answer_checker, link_checker], collector)
    # collector → manager (approve/reject decision)
    .add_edge(collector, manager_exec)
    # manager → switch: rejected → feedback → QA (loop), approved → output
    .add_switch_case_edge_group(
        manager_exec,
        [
            Case(condition=lambda d: not d.approved, target=feedback_exec),
            Default(target=output_exec),
        ],
    )
    # feedback → QA (loop back)
    .add_edge(feedback_exec, question_answerer)
    .build()
)

print("\n✅ Workflow built: QuestionAnswerer → [AnswerChecker, LinkChecker] → Manager (approve/reject loop)")


# ============================================================
# Launch DevUI
# ============================================================

print("\nStarting DevUI on http://localhost:8090")
print("Entities:")
print("  - QuestionAnswerer: MCP-grounded answers (Microsoft Learn)")
print("  - AnswerChecker: Independent verification (web search)")
print("  - LinkChecker: URL validation (HTTP requests)")
print("  - RFX QA Workflow: Full orchestrated workflow with graph")
print("\nTry: 'Does Azure support HIPAA compliance for healthcare workloads?'")

serve(
    entities=[question_answerer, answer_checker, link_checker, workflow],
    port=8090,
    auto_open=False,
    instrumentation_enabled=True,
)
