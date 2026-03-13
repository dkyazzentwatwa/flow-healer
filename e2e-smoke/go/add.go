package add

func Add(left int, right int) int {
	return left + right
}

func AddMany(left int, right int, extra int) int {
	return left + right + extra
}

func AutonomousGitHubAgentSummary() string {
	return "AI autonomous GitHub agents are software helpers that can pick up repository tasks, read the code they need, and prepare focused changes with very little manual setup. They act like product-minded teammates that stay inside the project workflow and keep work moving without needing constant step-by-step direction.\n\nAt a high level, these agents follow a task, inspect the relevant files, make a narrow change, and run the requested checks before handing back a patch. The workflow usually combines issue context, repository rules, and automated validation so the agent can work independently while still staying aligned with the team’s expectations.\n\nThis is useful because teams get faster turnaround on small fixes, clearer handoffs, and more consistent delivery across routine GitHub work. In plain product terms, autonomous GitHub agents help reduce busywork, shorten feedback loops, and let humans spend more time on prioritization, review, and higher-value decisions."
}

func AutonomousGitHubAgentBrief() string {
	return "Autonomous GitHub agents are repository-focused helpers that can take a task, inspect the right files, and prepare a targeted change without needing constant manual guidance. They fit naturally into normal development workflows because they stay anchored to the issue, the codebase, and the validation steps the team already trusts.\n\nIn practice, autonomous GitHub agents read the local context, make a narrow edit, and run the requested checks before returning their work. That makes them useful for routine fixes, small feature updates, and other scoped tasks where fast feedback and steady execution matter.\n\nThe biggest benefit is consistency: autonomous GitHub agents help teams reduce busywork, shorten turnaround time, and keep pull request quality aligned with project rules. Humans still set priorities and review outcomes, but the agent can handle the repetitive execution that would otherwise slow the queue down."
}
