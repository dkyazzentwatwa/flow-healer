---
name: multi-agent-orchestrator
description: "Activates a structured multi-agent workflow (Team Lead + specialized Employees) to handle complex tasks that require decomposition, specialized execution, and synthesis. Use when a user request: (1) Involves multiple distinct domains (e.g., research, coding, testing), (2) Is large enough to be split into parallel sub-tasks, (3) Requires high-quality synthesis of diverse inputs. Triggers on requests like: 'Research 3 competitors...', 'Build a feature with backend/frontend/testing...', 'Analyze a business idea with market/risk/monetization agents...'"
---

# Multi-Agent Orchestrator

This skill implements a rigorous Team Lead/Employee workflow to ensure complex missions are executed with precision, accountability, and high-quality synthesis.

## Core Roles

### 👤 Team Lead (Orchestrator)
The Team Lead is responsible for the mission's success. They interpret the request, break it down, delegate to specialized agents, and assemble the final output.

### 👥 Employee Agents (Specialists)
Employee agents own specific sub-tasks. They work within their assigned scope, report findings, and hand off deliverables to the Team Lead.

## Execution Workflow

1.  **Mission Analysis:** Identify if the task is complex enough for multi-agent delegation.
2.  **Task Breakdown & Kickoff:** Create a mission plan using the **Mission Kickoff** template in [templates.md](references/templates.md).
3.  **Delegation:** Assign specific **Task Briefs** to Employee agents.
4.  **Specialized Execution:** Employee agents perform their tasks according to the [protocols.md](references/protocols.md).
5.  **Quality Control & Synthesis:** Team Lead reviews handoffs and integrates them into a final response using the **Final Synthesis** template.

## Operational Standards

- **Templates:** Always use the standardized communication templates in [templates.md](references/templates.md).
- **Communication:** Every handoff must be explicit. No "invisible magic" between agents.
- **Rules of Engagement:** Strictly follow the parallel vs. sequential execution and conflict resolution rules in [protocols.md](references/protocols.md).
- **Final Result:** The Team Lead is solely responsible for producing a single, polished, and coherent final response that directly addresses the user's objective.

## Trigger Scenarios

- **Research:** "Analyze [Topic] from three different perspectives: [X], [Y], and [Z]."
- **Development:** "Build [Feature] with a backend API, a frontend UI, and a comprehensive test suite."
- **Analysis:** "Evaluate [Idea] for market fit, technical feasibility, and financial risk."
- **Content Creation:** "Write a marketing campaign including email copy, social media posts, and a landing page."
