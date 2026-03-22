
package parse

import (
	"testing"
)

func TestSystemPrompt(t *testing.T) {
	prompt := SystemPrompt()
	if prompt == "" {
		t.Error("SystemPrompt() returned empty string")
	}

	// Should contain key instructions
	expected := []string{"query parser", "subject-verb-object", "JSON"}
	for _, exp := range expected {
		if !contains(prompt, exp) {
			t.Errorf("SystemPrompt() should contain %q", exp)
		}
	}
}

func TestParseResult(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantErr bool
		check   func(*QueryResult)
	}{
		{
			name:    "valid full triplet",
			input:   `{"triplets": [{"subject": "cat", "verb": "eats", "object": "meat"}], "ambiguous": false}`,
			wantErr: false,
			check: func(r *QueryResult) {
				if len(r.Triplets) != 1 {
					t.Errorf("Triplets length = %v, want 1", len(r.Triplets))
					return
				}
				if r.Triplets[0].Subject != "cat" {
					t.Errorf("Subject = %v, want cat", r.Triplets[0].Subject)
				}
				if r.Triplets[0].Verb != "eats" {
					t.Errorf("Verb = %v, want eats", r.Triplets[0].Verb)
				}
				if r.Triplets[0].Object != "meat" {
					t.Errorf("Object = %v, want meat", r.Triplets[0].Object)
				}
				if r.Ambiguous {
					t.Error("Ambiguous should be false")
				}
			},
		},
		{
			name:    "partial triplet",
			input:   `{"triplets": [{"subject": "banana", "verb": "is", "object": ""}], "ambiguous": false}`,
			wantErr: false,
			check: func(r *QueryResult) {
				if len(r.Triplets) != 1 {
					t.Errorf("Triplets length = %v, want 1", len(r.Triplets))
					return
				}
				if r.Triplets[0].Subject != "banana" {
					t.Errorf("Subject = %v, want banana", r.Triplets[0].Subject)
				}
				if r.Triplets[0].Object != "" {
					t.Errorf("Object = %v, want empty", r.Triplets[0].Object)
				}
			},
		},
		{
			name:    "ambiguous query",
			input:   `{"triplets": [{"subject": "python", "verb": "", "object": "", "context": "programming"}], "ambiguous": true}`,
			wantErr: false,
			check: func(r *QueryResult) {
				if !r.Ambiguous {
					t.Error("Ambiguous should be true")
				}
				if len(r.Triplets) == 0 || r.Triplets[0].Context != "programming" {
					t.Errorf("Context = %v, want programming", r.Triplets[0].Context)
				}
			},
		},
		{
			name:    "invalid JSON",
			input:   `{"triplets": [{"subject": "cat", "verb"}]}`,
			wantErr: true,
		},
		{
			name:    "empty object allowed",
			input:   `{"triplets": [{"subject": "", "verb": "is", "object": ""}], "ambiguous": false}`,
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := ParseResult(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseResult() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && tt.check != nil {
				tt.check(result)
			}
		})
	}
}

func TestTripletIsQuestion(t *testing.T) {
	tests := []struct {
		name     string
		verb     string
		expected bool
	}{
		{"question with ?", "is?", true},
		{"statement without ?", "like", false},
		{"empty verb", "", false},
		{"question was?", "was?", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			triplet := Triplet{Verb: tt.verb}
			if got := triplet.IsQuestion(); got != tt.expected {
				t.Errorf("IsQuestion() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func TestTripletNormalizedVerb(t *testing.T) {
	tests := []struct {
		name     string
		verb     string
		expected string
	}{
		{"question with ?", "is?", "is"},
		{"statement without ?", "like", "like"},
		{"empty verb", "", ""},
		{"question was?", "was?", "was"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			triplet := Triplet{Verb: tt.verb}
			if got := triplet.NormalizedVerb(); got != tt.expected {
				t.Errorf("NormalizedVerb() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsAt(s, substr))
}

func containsAt(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
