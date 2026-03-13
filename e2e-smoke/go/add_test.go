package add

import (
	"strings"
	"testing"
)

func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Fatalf("Add(2, 3) = %d, want 5", got)
	}
}

func TestAddMany(t *testing.T) {
	if got := AddMany(2, 3, 4); got != 9 {
		t.Fatalf("AddMany(2, 3, 4) = %d, want 9", got)
	}
}

func TestAutonomousGitHubAgentSummaryHasThreeParagraphs(t *testing.T) {
	summary := AutonomousGitHubAgentSummary()
	paragraphs := strings.Split(summary, "\n\n")

	if len(paragraphs) != 3 {
		t.Fatalf("AutonomousGitHubAgentSummary() returned %d paragraphs, want 3", len(paragraphs))
	}

	for i, paragraph := range paragraphs {
		if strings.TrimSpace(paragraph) == "" {
			t.Fatalf("AutonomousGitHubAgentSummary() paragraph %d is empty", i+1)
		}
	}
}

func TestAutonomousGitHubAgentSummaryMentionsAutonomousGitHubAgents(t *testing.T) {
	summary := strings.ToLower(AutonomousGitHubAgentSummary())

	if !strings.Contains(summary, "autonomous github agents") {
		t.Fatalf("AutonomousGitHubAgentSummary() = %q, want mention of autonomous GitHub agents", summary)
	}
}
