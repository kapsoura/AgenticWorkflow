# Agentic AI - Elaborate Notes from Week 04 Presentation

## Overview
This document expands the contents of the presentation **"Agentic AI"** by Deepak Subramani, Associate Professor, Department of Computational and Data Science, Indian Institute of Science Bengaluru.[file:1] It covers the full topic flow of the slides, including the definition and hierarchy of agentic systems, augmented LLMs, workflow patterns, single-agent and multi-agent designs, interoperability standards such as MCP and A2A, evaluation methods, common pitfalls, anti-patterns, and a practical decision framework.[file:1]

## Agentic Systems
Agentic systems span a wide range, from a lightly augmented large language model to a fully autonomous system.[file:1] At the lower end, the model is enhanced with capabilities such as tools and memory; at the higher end, the system can perceive, reason, act, and evaluate with minimal step-by-step human direction.[file:1]

An agentic system is defined in the slides as a system in which an LLM controls a loop of perception, reasoning, action, and observation while pursuing a goal.[file:1] This means the model is not merely answering a single prompt once; instead, it operates iteratively, adapts to feedback, uses tools, and makes progress toward an objective over multiple steps.[file:1]

Core properties of agentic systems include:
- Goal-directed behavior, where the system works toward an objective rather than producing one isolated answer.[file:1]
- Multi-step execution, where planning and action unfold across multiple iterations.[file:1]
- Adaptivity, where the system can respond to failures and intermediate observations.[file:1]
- Tool use, where the LLM reaches beyond its own internal parameters to access external systems.[file:1]

The presentation also notes that the field is still evolving, so the precise definition of an agent is changing as capabilities improve.[file:1] Another important point is that agents can use other agents as tools, which leads naturally to sub-agent and multi-agent architectures.[file:1]

## Agentic Patterns
The slides describe patterns as reusable solutions to recurring design problems in agentic systems.[file:1] Instead of inventing control logic from scratch each time, engineers rely on patterns to match the structure of the solution to the structure of the problem.[file:1]

This pattern-oriented view matters because the main design question in agentic systems is not only what the LLM knows, but how the LLM is related to the work being done.[file:1] The presentation organizes this design space first through the hierarchy of autonomy and workflow patterns, and later through single-agent and multi-agent patterns.[file:1]

## Spectrum of Agency
The presentation introduces a spectrum of agency that asks how much autonomy is delegated to the system.[file:1] The spectrum moves from no autonomy, to augmented LLMs, to workflows, and finally to autonomous agents.[file:1]

The trade-offs become sharper as autonomy increases:[file:1]

| Dimension | Low autonomy | High autonomy |
|---|---|---|
| Autonomy | Low [file:1] | High [file:1] |
| Predictability | High [file:1] | Low [file:1] |
| Cost per task | Low [file:1] | High [file:1] |
| Flexibility | Low [file:1] | High [file:1] |

This is a central engineering trade-off in the lecture: higher autonomy often gives better flexibility and open-ended problem solving, but it also reduces predictability and raises cost.[file:1] The slide deck repeatedly recommends choosing the lowest level of autonomy that still solves the problem.[file:1]

## Three Levels of Agentic Systems
The slides divide agentic systems into three levels.[file:1]

### Level 1: Augmented LLM
This level consists of a single LLM call enhanced with tools, memory, and structured output.[file:1] It is still fundamentally a one-prompt interaction, but it is stronger than a plain model because it can retrieve data, call APIs, execute code, and return reliably structured results.[file:1]

### Level 2: Workflow Patterns
This level introduces orchestrated sequences such as chaining, routing, and parallelization.[file:1] Here the control flow is designed by the engineer, so the system can perform multi-step behavior without granting the model full open-ended autonomy.[file:1]

### Level 3: Autonomous Agents
This level supports open-ended goal pursuit using self-directed loops of planning, acting, observing, and replanning.[file:1] It is appropriate for long-horizon tasks and dynamic discovery, but it requires stronger guardrails such as error handling, state persistence, and human oversight.[file:1]

The presentation explicitly advises starting at the lowest level that solves the problem, because each higher level adds coordination complexity and operational risk.[file:1]

## Level 1: The Augmented LLM
The augmented LLM is presented as an LLM enhanced with three capabilities: tools, memory, and structured output.[file:1] Even though it answers a single prompt, it can now reach beyond its native context window.[file:1]

### Tools
The slides list examples of tools such as API calls, web search, code execution, and read/write access to files or systems.[file:1] Tools give the model access to capabilities that are impossible to emulate reliably with text generation alone.[file:1]

### Memory
The presentation distinguishes multiple forms of memory:[file:1]
- In-context working memory, which consists of what is currently inside the context window.[file:1]
- External stores, such as dense or sparse retrieval systems, which support persistent long-term access.[file:1]
- Conversation history, which provides continuity across turns or sessions.[file:1]

### Structured output
Structured output includes formats like JSON and is useful when the system needs reliable extraction or machine-readable responses.[file:1] This makes downstream automation easier and more dependable than free-form text alone.[file:1]

## Tool Calling Mechanics
Tool calling is described as a synchronous process in which the LLM pauses, a tool executes, the result is inserted into context, and the LLM continues generation.[file:1] The slides also mention that tool descriptions are part of the prompt or can be supplied through an MCP client from an MCP server.[file:1]

Important implementation details include:
- Parallel tool calls are possible and can reduce latency.[file:1]
- Developers must handle empty results, timeouts, and schema mismatches.[file:1]
- The full flow is user prompt -> LLM decision -> tool invocation -> result returned to context -> final response.[file:1]

This section emphasizes that agent reliability depends not just on model quality but also on robust handling of tool boundaries and failures.[file:1]

## Prompt and Context Structure
The lecture includes a slide on how an LLM call is structured.[file:1] The prompt stack can include the system prompt, user prompt, few-shot examples, tool descriptions, tool results, retrieved context, and optional reasoning prefixes.[file:1]

Each element has a distinct role:[file:1]
- The system prompt sets identity, behavior, constraints, and tool usage policy.[file:1]
- The user prompt contains the immediate task.[file:1]
- Few-shot examples demonstrate output style.[file:1]
- Tool descriptions define available functions and when they should be used.[file:1]
- Tool results act as observations from the environment.[file:1]
- Retrieved context supplies external knowledge before answering.[file:1]

This framing is useful because many failures in agentic systems come from poor prompt and context design rather than model weakness alone.[file:1]

## Level 2: Workflow Patterns
Workflow patterns coordinate multiple LLM calls or agents in a structured and often deterministic way.[file:1] In these systems, the engineer defines the control flow rather than leaving all decisions to the model.[file:1]

The presentation highlights five main workflow types:[file:1]
- Prompt chaining.[file:1]
- Routing.[file:1]
- Parallelization.[file:1]
- Orchestrator-subagent or orchestrator-worker patterns.[file:1]
- Evaluator-optimizer loops.[file:1]

These patterns are useful when tasks have recurring structure and when predictable control is preferable to fully autonomous planning.[file:1]

## Simple Workflows
The slides identify three simple workflows.[file:1]

### Chaining
Chaining is used when one step refines or transforms the output of the previous one, such as translate -> summarize -> format.[file:1] It is appropriate for sequential transformations with clear dependencies.[file:1]

### Routing
Routing is used when the type of input determines which specialized handler should be selected.[file:1] A classifier, simple rules, or a lightweight LLM call can dispatch each input to the correct path.[file:1]

### Parallelization
Parallelization is used when subtasks are independent and latency matters.[file:1] Running them simultaneously can reduce total response time before aggregation.[file:1]

## Orchestrator-Worker Pattern
The orchestrator-worker pattern is presented as a more intelligent workflow.[file:1] The orchestrator decomposes the task, delegates subtasks, and synthesizes the combined result.[file:1]

The presentation contrasts routing with orchestrator-subagent systems:[file:1]

| Question | Routing | Orchestrator-Subagent |
|---|---|---|
| Who decides which handler to call? | A classifier or simple rule [file:1] | An LLM reasoning about the task [file:1] |
| Is the handler list fixed? | Yes, defined at build time [file:1] | Can be dynamic [file:1] |
| Is there synthesis after dispatch? | No, each path is terminal [file:1] | Yes, the orchestrator assembles results [file:1] |
| Can the plan change from intermediate results? | No [file:1] | Yes [file:1] |
| Complexity of coordinated work | Low [file:1] | High [file:1] |

This distinction matters because routing is mainly about selecting one path, whereas orchestration is about decomposition, coordination, and synthesis across multiple subtasks.[file:1]

## Evaluator-Optimizer Pattern
In the evaluator-optimizer pattern, a generator produces an output, an evaluator scores it against a rubric, and the generator revises the result if the score is below a threshold.[file:1] This process can repeat until the output passes the threshold or the maximum number of rounds is reached.[file:1]

The slides stress that the evaluator's feedback must be actionable rather than just numeric.[file:1] They also note several evaluator options:[file:1]
- Rule-based evaluators such as schema validators or test runners, which are fast and deterministic.[file:1]
- LLM-as-judge evaluators using a rubric, which are more flexible for open-ended work.[file:1]
- Human evaluators for high-stakes or low-volume tasks.[file:1]

Stopping criteria may be threshold-based, round-based, or tied to explicit human approval.[file:1]

## Summary of the Hierarchy
By the end of the first major block, the presentation summarizes the hierarchy as follows:[file:1]
- Augmented LLM.[file:1]
- Workflow patterns, including prompt chaining, routing, parallelization, orchestrator-worker, and evaluator-optimizer.[file:1]
- Autonomous agents.[file:1]

This summary reinforces the main architectural ladder from minimal augmentation to open-ended autonomy.[file:1]

## Level 3: Autonomous Agents
Autonomous agents pursue open-ended goals without a pre-specified control flow.[file:1] They plan, act, observe, and replan dynamically.[file:1]

The lecture says these are appropriate for long-horizon tasks, ambiguous requirements, and tasks that require dynamic discovery.[file:1] The available toolset may include web search, code execution, file I/O, APIs, and even spawning sub-agents.[file:1]

Because these agents have more freedom, they also require stronger infrastructure:[file:1]
- Robust error handling.[file:1]
- State persistence.[file:1]
- Human oversight checkpoints.[file:1]

The slides list example frameworks such as LangGraph, AutoGPT-style loops, Claude Agent API, and OpenAI Assistants.[file:1]

## Single-Agent and Multi-Agent Patterns
The presentation then moves to a second major theme: autonomous single-agent and multi-agent patterns.[file:1]

### Single-agent patterns
Single-agent patterns use one LLM operating in a loop with tools and memory.[file:1] The slides mention ReAct, Reflection, and Plan-and-Execute as the main designs.[file:1]

### Multi-agent patterns
Multi-agent patterns use several LLMs coordinating toward a shared goal.[file:1] The examples given are hierarchical systems, peer-to-peer systems, adversarial systems, and assembly-line systems.[file:1]

The slides suggest choosing single-agent designs when the task fits in one context window, and multi-agent designs when it exceeds one agent's scope or capacity.[file:1]

## Single-Agent Pattern: ReAct
ReAct stands for reasoning plus acting.[file:1] In this pattern, the LLM alternates between reasoning about the next step, taking an action such as a tool call, observing the result, and repeating this loop until it can answer.[file:1]

The lecture notes several characteristics:[file:1]
- Thought traces are part of the prompt context rather than hidden.[file:1]
- ReAct works especially well when reasoning steps are verifiable, such as in mathematics, code, or factual lookup tasks.[file:1]
- A major weakness is compounding error when early reasoning is wrong.[file:1]
- A practical production recommendation is to cap the maximum number of iterations to prevent infinite loops.[file:1]

## Single-Agent Pattern: Reflection
Reflection is a single-agent pattern where the same agent generates a draft, critiques it against a rubric, and revises it.[file:1] Unlike evaluator-optimizer, this happens within one context window and does not require a separate evaluator agent.[file:1]

The presentation recommends reflection for creative writing, code review, and structured reports.[file:1] It also emphasizes that self-critique works only when the rubric is concrete and that revision rounds should usually be limited to one to three to control cost and latency.[file:1]

## Single-Agent Pattern: Plan-and-Execute
Plan-and-Execute separates planning from execution.[file:1] The agent first produces a complete plan and then executes it step by step.[file:1]

This has several benefits according to the slides:[file:1]
- The plan becomes visible and can be inspected.[file:1]
- Human review can be inserted before action begins.[file:1]
- The pattern suits structured and high-stakes tasks better than exploratory tasks.[file:1]

The presentation contrasts this with ReAct: ReAct performs implicit planning during each step, while Plan-and-Execute makes the plan explicit upfront.[file:1]

## Memory in Single Agents
A dedicated slide explains memory types for single agents.[file:1]

### Working memory
Working memory is whatever currently sits in the context window.[file:1] It is fast and precise, but limited by context length and lost after the session ends.[file:1]

### External memory
External memory stores long-term information in systems such as vector stores or databases.[file:1] It is persistent and scalable, but its usefulness depends strongly on retrieval quality.[file:1]

### Episodic memory
Episodic memory is conversation history from prior interactions, typically stored and summarized.[file:1] It supports continuity across sessions, but it needs compression to remain efficient.[file:1]

### Procedural memory
Procedural memory consists of skills and instructions encoded in the system prompt, tool descriptions, or learned workflows.[file:1] It is effectively built into the agent's behavior rather than dynamically retrieved.[file:1]

## Choosing a Single-Agent Pattern
The slides provide a small decision table that maps task characteristics to recommended patterns.[file:1]

| Task characteristic | Recommended pattern |
|---|---|
| Step-by-step lookup or research | ReAct [file:1] |
| Draft quality matters and a verifiable rubric exists | Reflection [file:1] |
| High-stakes task needing human approval before action | Plan-and-Execute [file:1] |
| Needs facts beyond the context window | External Memory + ReAct [file:1] |
| Continuation across sessions | Episodic Memory [file:1] |
| Simple Q&A with no external data | Augmented LLM without a loop [file:1] |

This section is valuable because it connects abstract patterns to concrete task properties.[file:1]

## Why Multi-Agent Systems?
The presentation lists several reasons to use multi-agent systems.[file:1]

- **Context limits:** tasks that exceed a single context window can be split across agents.[file:1]
- **Specialization:** different agents can be optimized for different subtasks using different models, prompts, or tools.[file:1]
- **Parallelism:** independent subtasks can run at the same time to reduce wall-clock latency.[file:1]
- **Error isolation:** failures in one agent do not have to cascade if retries or fallback agents exist.[file:1]
- **Verifiability:** dedicated critic or auditor agents can cross-check outputs.[file:1]
- **Scale:** more agents can handle more concurrent users or tasks.[file:1]

These benefits come with coordination overhead, so the architecture has to justify its own complexity.[file:1]

## Multi-Agent Coordination Patterns
The lecture introduces four broad coordination patterns.[file:1]
- Hierarchical.[file:1]
- Peer-to-peer.[file:1]
- Adversarial.[file:1]
- Assembly line.[file:1]

These patterns differ mainly in how work is divided, how agents communicate, and where synthesis or conflict resolution happens.[file:1]

## Hierarchical Pattern
In a hierarchical multi-agent pattern, one orchestrator decomposes the goal, delegates subtasks to specialized workers, collects their outputs, and synthesizes a final answer.[file:1]

The slides emphasize several design lessons:[file:1]
- The orchestrator needs broad awareness, while workers need deep but narrow expertise.[file:1]
- Task decomposition quality strongly affects total system quality.[file:1]
- Communication usually uses structured instructions such as JSON or templated natural language.[file:1]
- A common pitfall is over-micromanagement by the orchestrator instead of trusting worker outputs.[file:1]

## Peer-to-Peer and Adversarial Patterns
Peer-to-peer collaboration has agents communicating directly without a central coordinator.[file:1] Each agent has partial state, and the group may negotiate or vote to reach agreement.[file:1]

The slides say this is best suited for debate, voting, and consensus tasks.[file:1] By contrast, the adversarial or critic pattern assigns one agent to challenge another's output by identifying flaws, inconsistencies, or counterarguments.[file:1]

The adversarial pattern is recommended for fact-checking, red-teaming, contract review, and safety evaluation.[file:1] It differs from self-critique because the critic is a separate agent with a different prompt and perspective.[file:1]

## Assembly Line Pattern
The assembly-line pattern has each agent perform one specialized transformation before passing its output to the next stage.[file:1] The example flow shown is ingestion -> research -> drafting -> review -> formatting.[file:1]

Advantages listed in the slides include:[file:1]
- High modularity, because stages can be swapped or upgraded independently.[file:1]
- Ease of testing, because each stage can be validated in isolation.[file:1]
- Lower run cost for each individual agent, because each one is small and focused.[file:1]

Limitations include sequential latency, error propagation, and the need for schema contracts between agents.[file:1]

## Shared State and Context Management
Multi-agent systems need a way to share enough state for coordination without paying the cost of sharing everything.[file:1] The lecture gives four approaches.[file:1]

### Blackboard or shared memory
All agents read and write to a common structured store.[file:1] This is simple but requires locking to avoid race conditions.[file:1]

### Message passing
Agents communicate through explicit messages.[file:1] This is decoupled, auditable, and composable, and the slide notes that it is standard in the A2A protocol.[file:1]

### State summarization
A summary node compresses state at each handoff to fit the next agent's context window.[file:1] This reduces token cost and keeps the next agent focused.[file:1]

### Event streaming
Agents emit events that other components can subscribe to and react to.[file:1] This supports real-time coordination and monitoring.[file:1]

The key design rule in the lecture is to pass only the minimum state needed for the next agent to do its job.[file:1]

## Interoperability Problem
As agents become more common, they need standard ways to discover and use tools or communicate with other agents.[file:1] The presentation frames this as an interoperability problem that standards can solve.[file:1]

The two standards highlighted are:[file:1]
- MCP for agent-tool interoperability.[file:1]
- A2A for agent-agent interoperability.[file:1]

The slides illustrate that standards reduce the integration burden from an N x M custom integration problem to a much smaller protocol-based integration surface.[file:1]

## Model Context Protocol (MCP)
MCP is described as an open standard introduced by Anthropic for connecting AI agents to external data sources and tools.[file:1] The lecture uses the analogy that MCP is like a USB-C port for AI, because it provides a universal interface instead of requiring custom integration code for every tool.[file:1]

The rationale given for MCP includes:[file:1]
- Without MCP, every app must hard-code its tools.[file:1]
- When the LLM changes, integrations may need to be rewritten.[file:1]
- Interoperability across tools and tool-serving systems is difficult without a standard.[file:1]
- MCP separates capability providers from capability consumers.[file:1]

## MCP Host, Client, and Server
A dedicated slide explains the MCP architecture.[file:1]

- The **host** is the environment embedding the LLM and managing user interaction and the agent lifecycle.[file:1]
- The **client** is the protocol implementation layer inside the host that speaks MCP and manages connections to servers.[file:1]
- The **server** is an external process exposing tools, resources, or prompts through MCP.[file:1]

The presentation states that MCP uses JSON-RPC 2.0 over stdio or SSE, and that compliant servers advertise their tools while clients call them.[file:1] The design is described as stateless so that any compliant client can connect to any compliant server.[file:1]

## MCP Tool Invocation Flow
The slides show the full tool invocation loop under MCP.[file:1] The host application provides the prompt and tool list to the LLM through the MCP client, the LLM produces a tool call request, the tool is invoked on the MCP server, the result returns into context, and the LLM generates the final response.[file:1]

The lecture also identifies three primitive types that servers can expose:[file:1]
- Tools, which are callable functions like search, compute, or write.[file:1]
- Resources, which are readable data items such as files, database rows, or API responses.[file:1]
- Prompts, which are reusable prompt templates the host can inject.[file:1]

## Agent-to-Agent (A2A) Protocol
A2A is presented as a standard introduced by Google in 2025 for agent-to-agent delegation.[file:1] Its role is to let one agent communicate tasks to another regardless of framework or vendor.[file:1]

The slide states that an agent can be built with ADK or another framework, equipped with MCP or another tool standard, and still communicate through A2A with remote agents, local agents, and even humans.[file:1]

## A2A Specification Structure
The specification is presented in three layers.[file:1]

### Layer 1: Canonical Data Model
This layer defines the core data structures and message formats that all A2A implementations must understand.[file:1] The slides say these are protocol-agnostic definitions expressed as Protocol Buffer messages.[file:1]

### Layer 2: Abstract Operations
This layer describes the fundamental capabilities and behaviors that A2A agents must support, independent of the concrete transport protocol.[file:1]

### Layer 3: Protocol Bindings
This layer maps the abstract operations and data structures onto specific protocols such as JSON-RPC, gRPC, and HTTP/REST, including method names and endpoint patterns.[file:1]

## A2A vs MCP
The lecture directly compares A2A with MCP.[file:1]

| Aspect | MCP | A2A |
|---|---|---|
| Scope | Agent to tool [file:1] | Agent to agent [file:1] |
| Initiated by | LLM via client [file:1] | Calling agent [file:1] |
| Counterpart type | Any tool or resource [file:1] | Another LLM agent [file:1] |
| Discovery | Tool list in context [file:1] | Agent Card in JSON [file:1] |
| Output | Tool result [file:1] | Task artifact [file:1] |
| Use together? | Yes [file:1] | Yes [file:1] |

The key idea is that MCP and A2A are complementary rather than competing standards.[file:1]

## Why Agentic Systems Are Hard to Evaluate
The presentation explains that agentic systems are difficult to evaluate for several reasons.[file:1]

- **Non-determinism:** the same input may produce different action sequences.[file:1]
- **Long horizons:** errors compound over many steps and may appear late.[file:1]
- **Intermediate state ambiguity:** the final answer can be correct even if the path taken was poor.[file:1]
- **No ground truth:** many open-ended tasks have multiple valid trajectories.[file:1]
- **Side effects:** agents may write files, call APIs, or send emails, making errors harder to reverse.[file:1]
- **Evaluation cost:** running full end-to-end evaluations across many scenarios is expensive.[file:1]

This section highlights why classic one-shot benchmark thinking does not transfer cleanly to autonomous systems.[file:1]

## Outcome vs Trajectory Evaluation
The lecture distinguishes two evaluation styles.[file:1]

### Outcome evaluation
Outcome evaluation asks whether the agent completed the goal, how good the final output was, and how satisfied users were.[file:1] It is easier to collect and scales well for regression testing, but it can miss process failures, unnecessary steps, lucky successes, or mid-trajectory safety problems.[file:1]

### Trajectory evaluation
Trajectory evaluation asks whether the right tools were used in the right order, whether unnecessary steps were taken, whether tool inputs were well formed, and whether errors were handled gracefully.[file:1] It is more expensive because each step often needs labeling, but it is better for diagnosing root causes.[file:1]

The presentation recommends outcome evaluation for large-scale regression testing and trajectory evaluation when debugging or improving a particular failure mode.[file:1]

## Key Metrics for Agentic Systems
The slides list several operational metrics.[file:1]

| Metric | What it measures | How to compute |
|---|---|---|
| Task completion rate | Percentage of tasks fully completed [file:1] | Pass/fail on a benchmark task set [file:1] |
| Step efficiency | Steps taken versus minimum needed [file:1] | Trace step count against an oracle [file:1] |
| Tool accuracy | Correct tool calls over total calls [file:1] | Label each call as correct, wrong tool, or bad arguments [file:1] |
| Error recovery rate | Share of errors recovered from [file:1] | Inject failures and measure recovery [file:1] |
| Cost per task | Token cost plus API calls [file:1] | Sum token counts across steps [file:1] |
| Latency | Wall-clock completion time [file:1] | Measure end-to-end with step breakdown [file:1] |
| Safety violations | Harmful or irreversible actions [file:1] | Human review of flagged trajectories [file:1] |

These metrics show that agent performance is multi-dimensional; correctness alone is not sufficient.[file:1]

## Tracing, Logging, and Observability
The lecture argues that structured logging is essential for debugging agentic systems.[file:1] Without traces, it becomes nearly impossible to understand why a run failed.[file:1]

The slides recommend logging:[file:1]
- Every LLM call, including prompt, response, token count, and latency.[file:1]
- Every tool call, including tool name, inputs, outputs, and errors.[file:1]
- A trace ID for each top-level task and across sub-agents.[file:1]
- The agent's decision about which tool was selected and why.[file:1]

The observability tools named in the slides are LangSmith, Arize Phoenix, Braintrust, and OpenTelemetry.[file:1] The slide's rule of thumb is that if a failed run cannot be replayed step by step, logging is insufficient.[file:1]

## When Not to Use Agents
One of the most practical slides warns against using agents by default.[file:1] The recommendation is to prefer the simplest system that solves the problem because agents add cost, latency, and complexity.[file:1]

The slides give several examples:[file:1]
- For simple Q&A with no retrieval, use a single LLM call.[file:1]
- For fixed data transformations, use a non-LLM pipeline.[file:1]
- For known retrieval tasks, use a RAG pipeline.[file:1]
- For structured extraction from a document, use an augmented LLM with schema output.[file:1]
- When latency under one second is required, avoid agents because each additional hop adds delay.[file:1]
- When no human oversight is possible, avoid autonomous agents for irreversible actions.[file:1]

## Common Pitfall: Unbounded Loops
An unbounded loop is an agent that keeps spending tokens indefinitely without returning a result or escalating.[file:1] The slides identify root causes such as no max-iteration cap, stopping conditions that rely on the LLM deciding it is done, and circular tool dependencies.[file:1]

The proposed fixes are straightforward:[file:1]
- Set a hard step limit, such as a maximum number of iterations.[file:1]
- Use deterministic stopping based on tool results rather than model self-assessment.[file:1]
- Add infrastructure-level timeouts.[file:1]
- Log step count and alert on suspicious patterns.[file:1]

## Common Pitfall: Cascading Failures
The slides show how an error from one agent can silently propagate through later stages in a multi-agent pipeline.[file:1] For example, bad research can feed bad summaries, which then feed bad drafts and formatting.[file:1]

Recommended mitigations include:[file:1]
- Validation checkpoints between agents.[file:1]
- Critic agents or evaluator nodes before downstream handoff.[file:1]
- Designs that let agents signal uncertainty instead of silently passing errors.[file:1]
- Tests with known-bad inputs to verify whether propagation is detected.[file:1]

## Pitfalls: Context Mismanagement and Tool Trust
The presentation bundles several additional pitfalls.[file:1]

### Context window mismanagement
Multi-hop agents can accumulate too much context, causing overflow or noise.[file:1] The recommended fix is to summarize state at checkpoints, evict stale tool results, and move long-run state into external memory.[file:1]

### Tool trust without verification
Agents may treat tool outputs as unquestioned truth, even when a web result is hallucinated or a database record is stale.[file:1] The slides recommend confidence checks and independent verification before irreversible actions.[file:1]

### Prompt injection via tool results
Tool outputs can contain adversarial text such as instructions that try to override the agent's prior rules.[file:1] The presentation recommends sanitizing tool outputs, separating context sections, and applying input validation.[file:1]

### State reset between hops
In some systems, state is accidentally reset between agent steps, causing lost retrieval or lost tool results.[file:1] The recommended fix is to treat state as additive and explicitly pass accumulated context at each step.[file:1]

## Anti-Patterns in Agentic Systems
The slides list several high-level anti-patterns.[file:1]

- **Over-orchestration:** using many agents when one would do the job.[file:1]
- **Prompt sprawl:** long, unreviewed prompts across multiple agents causing inconsistency and poor debuggability.[file:1]
- **No human-in-the-loop:** giving agents full write access to production systems without approval gates.[file:1]
- **Treating the LLM as an oracle:** passing generated reasoning downstream without verification.[file:1]
- **Agent soup:** adding more agents to hide a prompt or data problem instead of fixing the root cause.[file:1]

These anti-patterns share one theme: complexity is often mistaken for capability.[file:1]

## No Human-in-the-Loop
A separate slide emphasizes that the highest-risk anti-pattern is allowing autonomous agents to perform irreversible actions such as sending emails, deleting data, or making payments without human approval.[file:1]

The presentation recommends several controls:[file:1]
- Classify every tool by reversibility before deployment.[file:1]
- Require explicit human confirmation for irreversible tools.[file:1]
- Show humans a summary of what the agent intends to do before execution.[file:1]
- Log all irreversible actions with rationale for later audit.[file:1]

The slide also presents a reversibility spectrum from low-risk read-only actions to high-risk send or execute actions.[file:1]

## Minimal Viable Agent
One of the most actionable parts of the lecture is the minimal viable agent strategy.[file:1] The advice is to start with the least agentic system that could work and add autonomy only when evidence shows it is needed.[file:1]

The five-step path in the slides is:[file:1]
1. Build a single LLM call first.[file:1]
2. Add tools only if context is insufficient, one at a time.[file:1]
3. Add a loop only if a single pass fails, starting with a low iteration cap.[file:1]
4. Add multiple agents only for specialization or scale.[file:1]
5. Add stronger autonomy only after observing many successful runs and building trust.[file:1]

This is effectively an engineering maturity model for agent systems.[file:1]

## Production Advice
The final practical advice slide frames production agents as systems that need the same rigor as software engineering.[file:1]

The specific recommendations are:[file:1]
- Prompt agents the way a new employee would be onboarded: clearly define goals, constraints, tools, and what done means.[file:1]
- Invest in evaluation before scaling, because prompt or tool changes can silently break behavior.[file:1]
- Make failures loud instead of silently returning partial results.[file:1]
- Design for cost from the start, since model usage compounds across steps.[file:1]
- Treat prompts as code by version-controlling and reviewing them.[file:1]

## Decision Framework
The presentation ends with a clear decision framework for what to build.[file:1] The logic is based on three key questions.[file:1]

1. Does the task need external data or tools?[file:1]
   - If no, use a single LLM call.[file:1]
2. If yes, is the flow fixed or known upfront?[file:1]
   - If yes, use a workflow pattern.[file:1]
3. If the flow is not fixed, does the task need multiple specialists or agents?[file:1]
   - If no, use a single autonomous agent.[file:1]
   - If yes, use a multi-agent system.[file:1]

This framework ties together the whole lecture: select architecture based on task structure, not based on hype.[file:1]

## Closing Interpretation
Across the slides, the strongest recurring message is architectural restraint.[file:1] Agentic systems are powerful, but higher autonomy is not automatically better; each step up the hierarchy should be justified by a real task need, supported by evaluation, and protected by observability and human oversight.[file:1]

The presentation therefore treats agent design not as a race toward full autonomy, but as a disciplined engineering practice grounded in choosing the simplest reliable system first.[file:1]
