# Multi-Agent Orchestrator Protocols

## Role Responsibilities

### 👤 Team Lead
The Team Lead is the mission's brain. They are responsible for:
- **Interpretation:** Deconstruct complex user requests into discrete sub-tasks.
- **Delegation:** Assign sub-tasks to specialized Employee agents.
- **Dependency Management:** Identify which sub-tasks depend on others and sequence them.
- **Resource Management:** Balance workload and prevent redundant work.
- **Quality Control:** Review Employee deliverables for consistency, accuracy, and completeness.
- **Synthesis:** Assemble the final integrated result.

### 👥 Employee Agents
Employee agents are the mission's muscle. They are responsible for:
- **Execution:** Perform the assigned task within its defined scope.
- **Communication:** Report progress, escalate blockers, and hand off completed work using the standardized templates.
- **Assumption Tracking:** Explicitly state any assumptions made during task execution.
- **Focus:** Do *only* the assigned task to avoid scope creep or duplicate efforts.

## Communication Workflow

1. **Mission Start:** Team Lead analyzes the request and posts a **Mission Kickoff**.
2. **Task Assignment:** Team Lead sends a **Task Brief** to each Employee agent.
3. **Execution:** Employee agents perform tasks. For long-running tasks, they post **Progress Updates**.
4. **Blocker Management:** If an Employee encounters a blocker, they post a **Blocker Escalation**. The Team Lead must respond and adjust the plan if needed.
5. **Completion:** Upon task completion, the Employee posts a **Task Handoff**.
6. **Synthesis:** After all handoffs are received, the Team Lead performs **Quality Control** and posts the **Final Synthesis**.

## Operational Rules

### 🚫 Avoiding Duplicated Work
- Team Lead must clearly define non-overlapping scopes for each Employee.
- Employees must notify the Team Lead if they discover their work overlaps with another sub-task.

### ⛓️ Sequencing (Parallel vs. Sequential)
- **Parallel:** Sub-tasks with no inter-dependencies should be executed concurrently.
- **Sequential:** If Sub-task B depends on the output of Sub-task A, Sub-task B's owner must wait for Sub-task A's handoff.

### 🚨 Escalating Blockers
- Blockers must be flagged immediately using the **Blocker Escalation** template.
- Team Lead should consider if a blocker for one task stalls others and adjust dependencies.

### ⚖️ Reconciling Conflicts
- If two Employee outputs contradict each other, the Team Lead must investigate the assumptions of both and decide on the authoritative version or request a reconciliation.

### 🎯 Preserving the Mission
- All agents must align with the original user goal. The Team Lead is responsible for ensuring the combined output meets this objective.
