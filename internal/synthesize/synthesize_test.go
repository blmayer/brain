
package synthesize

import (
	"brain/internal/search"
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

	prompt := SystemPrompt(triplets)

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
	prompt := SystemPrompt([]search.Triplet{})

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
				{
					Subject:    "banana",
					Verb:       "is",
					Object:     "fruit",
					Confidence: 0.95,
					Source:     "test",
				},
			},
			want: "banana is fruit (confidence: 0.95, source: test)",
		},
		{
			name: "multiple triplets",
			triplets: []search.Triplet{
				{Subject: "cat", Verb: "is", Object: "mammal", Confidence: 0.95, Source: "test"},
				{Subject: "cat", Verb: "has", Object: "fur", Confidence: 0.90, Source: "test"},
			},
			want:     "cat is mammal (confidence: 0.95, source: test)",
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
				if !contains(result, tt.want) {
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

