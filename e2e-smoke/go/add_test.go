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

func TestAddManyVariadicSum(t *testing.T) {
	testCases := []struct {
		name   string
		inputs []int
		want   int
	}{
		{name: "three numbers", inputs: []int{1, 2, 3}, want: 6},
		{name: "mix of negative and positive", inputs: []int{-2, 4, 3}, want: 5},
		{name: "no inputs", inputs: nil, want: 0},
		{name: "single value", inputs: []int{7}, want: 7},
		{name: "longer list", inputs: []int{1, 2, 3, 4, 5}, want: 15},
	}

	for _, tc := range testCases {
		if got := AddMany(tc.inputs...); got != tc.want {
			t.Fatalf("AddMany(%v) = %d, want %d", tc.inputs, got, tc.want)
		}
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

func TestAutonomousGitHubAgentBriefHasThreeParagraphs(t *testing.T) {
	brief := AutonomousGitHubAgentBrief()
	paragraphs := strings.Split(brief, "\n\n")

	if len(paragraphs) != 3 {
		t.Fatalf("AutonomousGitHubAgentBrief() returned %d paragraphs, want 3", len(paragraphs))
	}

	for i, paragraph := range paragraphs {
		if strings.TrimSpace(paragraph) == "" {
			t.Fatalf("AutonomousGitHubAgentBrief() paragraph %d is empty", i+1)
		}
	}
}

func TestAutonomousGitHubAgentBriefMentionsAutonomousGitHubAgents(t *testing.T) {
	brief := strings.ToLower(AutonomousGitHubAgentBrief())

	if !strings.Contains(brief, "autonomous github agents") {
		t.Fatalf("AutonomousGitHubAgentBrief() = %q, want mention of autonomous GitHub agents", brief)
	}
}
