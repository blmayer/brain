

package synthesize

import (
	"brain/internal/search"
	"strings"
	"testing"
)

func TestSystemPrompt(t *testing.T) {
	triplets := []search.Triplet{
		{
			Subject:   "banana",
			Verb:      "is",
			Object:    "fruit",
			Confidence: 0.95,
			Source:    "test",
		},
	}

	prompt := SystemPrompt(triplets, nil)

	if prompt == "" {
		t.Error("SystemPrompt() returned empty string")
	}

	// Should contain key elements
	expected := []string{"knowledge synthesizer", "triplet", "confidence"}
	for _, exp := range expected {
		if !contains(prompt, exp) {
			t.Errorf("SystemPrompt() should contain %q", exp)
		}
	}

	// Should contain the triplet data
	if !contains(prompt, "banana") {
		t.Error("SystemPrompt() should contain triplet subject")
	}
}

func TestSystemPromptEmptyTriplets(t *testing.T) {
	prompt := SystemPrompt([]search.Triplet{}, nil)

	if !contains(prompt, "No triplets found") {
		t.Error("SystemPrompt() should indicate no triplets found")
	}
}

func TestFormatTriplets(t *testing.T) {
	tests := []struct {
		name     string
		triplets []search.Triplet
		want     string
	}{
		{
			name:     "empty",
			triplets: []search.Triplet{},
			want:     "(No triplets found)",
		},
		{
			name: "single triplet",
			triplets: []search.Triplet{
				{Subject: "banana", Verb: "is", Object: "fruit", Confidence: 0.95, Source: "test"},
			},
			want:     "banana is fruit",
		},
		{
			name: "multiple triplets",
			triplets: []search.Triplet{
				{Subject: "cat", Verb: "is", Object: "mammal", Confidence: 0.95, Source: "test"},
				{Subject: "cat", Verb: "has", Object: "fur", Confidence: 0.90, Source: "test"},
			},
			want:     "cat is mammal",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := formatTriplets(tt.triplets)
			if tt.want == "(No triplets found)" {
				if result != tt.want {
					t.Errorf("formatTriplets() = %v, want %v", result, tt.want)
				}
			} else {
				// For non-empty, just check it contains the key parts
				if !strings.Contains(result, tt.want) {
					t.Errorf("formatTriplets() should contain %v", tt.want)
				}
			}
		})
	}
}


func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || containsAt(s, substr))
}

func containsAt(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// TestGeneratePlanForSumProgram verifies that the generated PlanNode
// matches the expected structure for the sum program.
func TestGeneratePlanForSumProgram(t *testing.T) {
	plan := GeneratePlanForSumProgram()

	// Check the root node
	if plan.Name != "print" {
		t.Errorf("Expected root node to be 'print', got '%s'", plan.Name)
	}

	// Check that 'print' has one dependency: 'sum'
	if len(plan.Depends) != 1 {
		t.Errorf("Expected 'print' to have 1 dependency, got %d", len(plan.Depends))
	}

	sumNode := plan.Depends[0]
	if sumNode.Name != "sum" {
		t.Errorf("Expected 'sum' node as dependency of 'print', got '%s'", sumNode.Name)
	}

	// Check that 'sum' has two dependencies: 'a' and 'b'
	if len(sumNode.Depends) != 2 {
		t.Errorf("Expected 'sum' to have 2 dependencies, got %d", len(sumNode.Depends))
	}

	aNode := sumNode.Depends[0]
	bNode := sumNode.Depends[1]

	// Check 'a' node
	if aNode.Name != "a" {
		t.Errorf("Expected first dependency of 'sum' to be 'a', got '%s'", aNode.Name)
	}

	// Check 'a' dependencies
	if len(aNode.Depends) != 2 {
		t.Errorf("Expected 'a' to have 2 dependencies, got %d", len(aNode.Depends))
	}

	for _, dep := range aNode.Depends {
		if dep.Name != "declaration" && dep.Name != "read" {
			t.Errorf("Expected 'a' dependencies to be 'declaration' or 'read', got '%s'", dep.Name)
		}
	}

	// Check 'b' node
	if bNode.Name != "b" {
		t.Errorf("Expected second dependency of 'sum' to be 'b', got '%s'", bNode.Name)
	}

	// Check 'b' dependencies
	if len(bNode.Depends) != 2 {
		t.Errorf("Expected 'b' to have 2 dependencies, got %d", len(bNode.Depends))
	}

	for _, dep := range bNode.Depends {
		if dep.Name != "declaration" && dep.Name != "read" {
			t.Errorf("Expected 'b' dependencies to be 'declaration' or 'read', got '%s'", dep.Name)
		}
	}
}

