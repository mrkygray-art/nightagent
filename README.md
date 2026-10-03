# NightAgent

**AI-powered after-hours service intake, triage, ticket lifecycle, customer follow-up, opportunity handoff, and agent QA.**

NightAgent is a portfolio demonstration of how an AI voice agent can support the complete after-hours service lifecycle for a physical-security integrator. Instead of stopping at a chatbot or voice demo, NightAgent connects the customer conversation to operational workflow: capture the problem, create and prioritize a service ticket, simulate dispatch and repair progression, call the customer back, verify the outcome, identify follow-up sales or service needs, and regression-test agent behavior against problems found during real demo calls.

**Live demo:** https://nightshift-dispatch.vercel.app/demo  
**Agent QA Lab:** https://nightshift-dispatch.vercel.app/lab

> **Demo note:** The customer/AI interaction demonstrates the conversational experience. Dispatch, technician assignment, repair timing, and lifecycle progression are intentionally accelerated/simulated so a recruiter or reviewer can experience an hours-long service workflow in minutes. The UI labels simulated events accordingly.

## Why I Built It

After-hours service is more than answering a phone call. A useful system has to understand what happened, determine urgency, capture enough information for service, keep the customer informed, and make sure the issue is actually resolved.

NightAgent demonstrates how AI can sit inside that workflow rather than exist as a standalone assistant. The QA Lab extends that idea by showing that a production-style agent also needs repeatable evaluation: when a problem is discovered in a live conversation, it can become a regression test that protects the behavior going forward.

## Two Ways to Explore the Demo

### Simple Mode

Simple Mode is designed for a recruiter, hiring manager, customer, or business stakeholder. It keeps the experience focused on the customer journey: talk to Sam, create a ticket, follow the service lifecycle, and see the post-service callback and downstream actions.

### Engineering Mode

Engineering Mode exposes what is happening behind each conversational turn. It shows the path from caller audio through speech-to-text, agent reasoning, tool calls, deterministic business rules, persistence, voice response, and grading.

The goal is to make the implementation inspectable rather than presenting the voice agent as a black box.

```text
Caller audio
   |
   v
Speech to text
   |
   v
Agent decision
   |
   v
Tool call
   |
   v
Rules in Python/FastAPI
   |
   v
Record saved in Supabase
   |
   v
Voice response
   |
   v
Evaluation / grading
```

## Agent QA Lab

The **Agent QA Lab** turns problems discovered during live conversations into repeatable regression tests. The tests run against the live ElevenLabs agents using ElevenLabs Agent Testing, and NightAgent reads the latest results back into a recruiter-friendly QA dashboard.

This is intentionally different from a static scripted demo. The project demonstrates an engineering feedback loop:

```text
Live conversation
   |
   v
Unexpected or incorrect behavior found
   |
   v
Create a regression test
   |
   v
Run test against the live agent
   |
   v
Inspect reply + tool behavior
   |
   v
Pass / fail result
   |
   +----> Fix agent or workflow ----> Re-test
```

### Current regression coverage

| Test | What it protects |
| --- | --- |
| **QA-01 — Confirm identity after lookup** | Sam reads the caller's name and phone number back after account lookup and asks for confirmation. |
| **QA-02 — No ticket before confirmation** | Prevents `create_ticket` from running before the caller confirms identity details. |
| **QA-03 — Gate stuck open = emergency** | Verifies that a site that cannot be secured is classified as `cannot_secure_site` with emergency priority. |
| **QA-04 — Explain after-hours billing when applicable** | Confirms Sam gives the callback window, ticket number, and billing notice for a plan without after-hours coverage. |
| **QA-05 — Do not invent an extra charge** | Ensures a customer with 24/7 coverage is not incorrectly told that after-hours service costs extra. |
| **QA-06 — Handle an off-topic request safely** | Tests an unexpected hamburger-and-soda request and verifies Sam stays within the supported security/service scope. |
| **QA-07 — Repair first when a caller asks for a supervisor** | Ensures an active broken-gate emergency creates the repair ticket before the complaint/escalation workflow. |
| **QA-08 — Agent identity after handoff** | Verifies Jordan speaks as Jordan in the first person and does not promise a refund or credit. |

The lab evaluates both **reply behavior** and **tool behavior**. That distinction matters: an agent can sound correct while still calling the wrong tool, using the wrong parameters, or taking an action too early.

The public QA view intentionally exposes only safe evaluation data such as agent replies, tool names, tool parameters, test rationale, and pass/fail status. Sensitive request headers and tool secrets returned by upstream APIs are not passed to the page.

## End-to-End Workflow

1. **Customer calls the after-hours AI agent** and describes a security-system problem.
2. **AI gathers context** such as customer/account information, affected system, symptoms, and safety information.
3. **A service ticket is created** with a ticket number, issue classification, and rules-based priority.
4. **The ticket enters the service lifecycle** and progresses through notification, assignment, travel, arrival, repair, and check-in stages.
5. **NightAgent follows up with the customer** after the simulated repair to verify that the system is working.
6. **The customer can report that the problem remains**, allowing the workflow to continue instead of treating technician completion as proof of resolution.
7. **Additional needs are captured.** For example, a customer can request additional access-control doors and a quote.
8. **NightAgent creates downstream work** such as an opportunity and account-executive callback task.
9. **The lifecycle closes with an auditable history** showing the original call, service activity, check-in, outcome, and next actions.
10. **Agent behavior is regression-tested** so issues discovered during calls can become repeatable QA cases.

## Screenshots

### 1. After-hours AI intake and live ticket board
The customer starts an after-hours call with Sam while the ticket board provides an operational view of current service requests.

![NightAgent after-hours intake](docs/Screenshot%202026-10-02%20122730.png)

### 2. Conversational account and issue discovery
The agent gathers customer/account information and asks what is happening with the security system.

![NightAgent conversational intake](docs/Screenshot%202026-10-02%20122812.png)

### 3. AI conversation creates a service ticket
Information collected during the call becomes a structured service request visible on the ticket board.

![NightAgent ticket creation](docs/Screenshot%202026-10-02%20122943.png)

### 4. Accelerated service lifecycle
Demo mode moves the ticket through an intentionally accelerated workflow so the complete service lifecycle can be evaluated without waiting hours for a real dispatch.

![NightAgent service lifecycle](docs/Screenshot%202026-10-02%20123003.png)

### 5. Technician progression and operational timeline
The ticket records simulated notification, technician assignment, travel, arrival, and subsequent service events as a timeline.

![NightAgent technician progression](docs/Screenshot%202026-10-02%20123014.png)

### 6. Post-service AI check-in
After the repair stage, NightAgent initiates a customer check-in rather than assuming that a completed technician visit means the problem is solved.

![NightAgent customer check-in](docs/Screenshot%202026-10-02%20123022.png)

### 7. Follow-up needs captured during the conversation
The customer can ask for additional help during the follow-up—for example, requesting more access-control doors and a quote.

![NightAgent additional needs](docs/Screenshot%202026-10-02%20123032.png)

### 8. Service-to-sales handoff
NightAgent turns a newly discovered customer need into downstream action instead of allowing it to disappear inside a service conversation.

![NightAgent opportunity handoff](docs/Screenshot%202026-10-02%20123148.png)

### 9. Closed-loop lifecycle
The final ticket view connects the service outcome with next actions, including an access-control expansion opportunity and account-executive follow-up tasks.

![NightAgent closed-loop workflow](docs/Screenshot%202026-10-02%20123203.png)

## What the Project Demonstrates

- Conversational AI applied to a real business workflow
- ElevenLabs voice-agent integration
- Simple stakeholder view plus inspectable Engineering Mode
- After-hours customer intake
- Physical-security service triage
- Structured ticket creation from natural-language conversations
- Rules-based service prioritization
- Tool calling with deterministic business logic
- Human/service-team handoff
- Stateful ticket lifecycle tracking
- Customer follow-up after service
- Resolution verification rather than simple ticket completion
- Identification of additional customer needs
- Service-to-sales opportunity creation
- Account Executive follow-up tasks
- Regression testing based on failures found in live calls
- Reply-level and tool-level agent evaluation
- Multi-agent QA coverage for Sam and Jordan
- Safe public presentation of test results without exposing tool secrets
- Clear separation between AI behavior and simulated demo events
- Recruiter-friendly visualization of an end-to-end AI workflow

## Physical-Security Context

The demo scenarios are based on the kinds of problems a security integrator encounters in the field, including:

- Access-control doors or badges not working
- Main entrances that will not unlock
- Cameras stopping after a power outage
- Gates or doors stuck open
- After-hours coverage and escalation questions
- Multi-door access-control expansion requests

This is intentional: NightAgent combines my physical-security / Sales Engineering background with AI application development rather than demonstrating AI with a generic use case.

## Architecture Concept

```text
Customer
   |
   v
ElevenLabs Voice Agent
   |
   +--> Customer & account identification
   +--> Problem discovery
   +--> Safety / urgency questions
   +--> Tool calls
   |
   v
Python / FastAPI Service Workflow
   |
   +--> Ticket creation
   +--> Classification
   +--> Rules-based priority
   +--> Dispatch / assignment lifecycle
   +--> Status timeline
   |
   v
Supabase Persistence
   |
   v
Post-Service AI Check-In
   |
   +--> Confirm resolved -----------------> Close ticket
   |
   +--> Still broken ---------------------> Continue service workflow
   |
   +--> Additional need -----------------> Opportunity + AE task

Engineering feedback loop
   |
   +--> Live-call problem
   +--> ElevenLabs Agent Testing regression case
   +--> Reply/tool evaluation
   +--> Pass/fail result in Agent QA Lab
```

## Technology Stack

- **ElevenLabs Agents** — real-time conversational voice experience and agent testing
- **Python** — service orchestration and business logic
- **FastAPI** — API/tool endpoints used by the agents and demo
- **Supabase** — persisted ticket, lifecycle, and demo records
- **Vercel** — public demo hosting
- **ElevenLabs Agent Testing** — regression suites against live agents
- **Rules-based decision logic** — deterministic priority and workflow behavior where business rules should control the outcome

## Product Design Decisions

**AI does not determine everything.** The interface explicitly communicates when business rules—not the AI—set service priority.

**Simulation is labeled.** Technician assignment and time-based service progression are fictional demo events and are identified as simulated in the application.

**Completion is not the same as resolution.** NightAgent checks with the customer after service to determine whether the problem was actually fixed.

**Service conversations can contain revenue signals.** A customer mentioning additional doors, upgrades, or another need can become structured follow-up instead of an untracked comment.

**Agent failures become tests.** Problems found while exercising the live agent are converted into regression cases instead of being treated as one-off prompt fixes.

**Words and actions are tested separately.** The QA Lab checks both what an agent says and what tools it calls, including important parameters and action order.

**The lifecycle matters more than the chatbot.** The goal is to demonstrate orchestration across intake, operations, customer experience, sales, and AI quality—not simply an AI conversation window.

## Business Value

NightAgent explores how an integrator could reduce after-hours response friction while improving the quality of information handed to technicians. The same workflow can also improve customer communication and preserve sales opportunities discovered during service interactions.

The QA layer addresses a second business problem: conversational agents change as prompts, tools, and workflows evolve. Regression testing provides a way to verify that important behaviors—identity confirmation, emergency handling, billing language, escalation order, and agent identity—continue to work after those changes.

The concept is particularly relevant to security integrators, managed service providers, field-service organizations, and other businesses where an incoming customer problem must move through multiple people and systems before it is truly resolved.

## Portfolio Focus

NightAgent was built as an applied AI workflow project demonstrating the intersection of:

**AI + Voice Agents + Agent Evaluation + Physical Security + Customer Experience + Service Operations + Sales Engineering**

The project is designed to show how I approach a business problem from the initial customer interaction through operational execution, measurable next actions, and repeatable QA—not just how to connect an LLM to a user interface.
