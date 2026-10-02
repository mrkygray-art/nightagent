# NightAgent

**AI-powered after-hours service intake, triage, ticket lifecycle, customer follow-up, and opportunity handoff.**

NightAgent is a portfolio demonstration of how an AI voice agent can support the complete after-hours service lifecycle for a physical-security integrator. Instead of stopping at a chatbot or voice demo, NightAgent connects the customer conversation to operational workflow: capture the problem, create and prioritize a service ticket, simulate dispatch and repair progression, call the customer back, verify the outcome, and identify follow-up sales or service needs.

> **Demo note:** The customer/AI interaction demonstrates the conversational experience. Dispatch, technician assignment, repair timing, and lifecycle progression are intentionally accelerated/simulated so a recruiter or reviewer can experience an hours-long service workflow in minutes. The UI labels simulated events accordingly.

## Why I Built It

After-hours service is more than answering a phone call. A useful system has to understand what happened, determine urgency, capture enough information for service, keep the customer informed, and make sure the issue is actually resolved.

NightAgent demonstrates how AI can sit inside that workflow rather than exist as a standalone assistant.

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
- After-hours customer intake
- Physical-security service triage
- Structured ticket creation from natural-language conversations
- Rules-based service prioritization
- Human/service-team handoff
- Stateful ticket lifecycle tracking
- Customer follow-up after service
- Resolution verification rather than simple ticket completion
- Identification of additional customer needs
- Service-to-sales opportunity creation
- Account Executive follow-up tasks
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
AI Voice / Conversation Layer
   |
   +--> Customer & account identification
   +--> Problem discovery
   +--> Safety / urgency questions
   |
   v
Service Workflow
   |
   +--> Ticket creation
   +--> Classification
   +--> Rules-based priority
   +--> Dispatch / assignment lifecycle
   +--> Status timeline
   |
   v
Post-Service AI Check-In
   |
   +--> Confirm resolved -----------------> Close ticket
   |
   +--> Still broken ---------------------> Continue service workflow
   |
   +--> Additional need -----------------> Opportunity + AE task
```

## Product Design Decisions

**AI does not determine everything.** The interface explicitly communicates when business rules—not the AI—set service priority.

**Simulation is labeled.** Technician assignment and time-based service progression are fictional demo events and are identified as simulated in the application.

**Completion is not the same as resolution.** NightAgent checks with the customer after service to determine whether the problem was actually fixed.

**Service conversations can contain revenue signals.** A customer mentioning additional doors, upgrades, or another need can become structured follow-up instead of an untracked comment.

**The lifecycle matters more than the chatbot.** The goal is to demonstrate orchestration across intake, operations, customer experience, and sales—not simply an AI conversation window.

## Business Value

NightAgent explores how an integrator could reduce after-hours response friction while improving the quality of information handed to technicians. The same workflow can also improve customer communication and preserve sales opportunities discovered during service interactions.

The concept is particularly relevant to security integrators, managed service providers, field-service organizations, and other businesses where an incoming customer problem must move through multiple people and systems before it is truly resolved.

## Portfolio Focus

NightAgent was built as an applied AI workflow project demonstrating the intersection of:

**AI + Physical Security + Customer Experience + Service Operations + Sales Engineering**

The project is designed to show how I approach a business problem from the initial customer interaction through operational execution and measurable next actions—not just how to connect an LLM to a user interface.
