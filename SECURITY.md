# Security Policy

## Supported Versions

Security fixes are applied on a best-effort basis to the latest code on the default branch.
Older branches or forks may not receive coordinated fixes.

## Reporting a Vulnerability

Please do not report security vulnerabilities in public issues, pull requests, or discussions.

If GitHub Private Vulnerability Reporting is enabled for this repository, use that channel.
Otherwise, contact the project maintainers through a private maintainer contact channel before
public disclosure.

When reporting a vulnerability, include:

- A clear description of the issue
- Affected files, modules, or endpoints
- Reproduction steps or a minimal proof of concept
- Impact assessment, if known
- Any suggested remediation or mitigation

## Response Expectations

Maintainers will try to:

- Acknowledge a report within 3 business days
- Confirm whether the issue is in scope
- Share status updates as remediation work progresses
- Credit the reporter if they want to be acknowledged

## In Scope

Examples of issues that should be reported through this policy include:

- Authentication or authorization bypasses
- Secret exposure
- Command execution or sandbox escape risks
- Unsafe file writes or path traversal
- Data corruption or integrity issues with security impact
- Vulnerable dependency or CI workflow configurations with real exploitability

## Disclosure

Please allow maintainers reasonable time to investigate, remediate, and publish a fix before
public disclosure.
