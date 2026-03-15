
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
		name     string
		input    string
		wantErr  bool
		check    func(*QueryResult)
	}{
		{
			name:    "valid full triplet",
			input:   `{"subject": "cat", "verb": "eats", "object": "meat", "ambiguous": false}`,
			wantErr: false,
			check: func(r *QueryResult) {
				if r.Subject != "cat" {
					t.Errorf("Subject = %v, want cat", r.Subject)
				}
				if r.Verb != "eats" {
					t.Errorf("Verb = %v, want eats", r.Verb)
				}
				if r.Object != "meat" {
					t.Errorf("Object = %v, want meat", r.Object)
				}
				if r.Ambiguous {
					t.Error("Ambiguous should be false")
				}
			},
		},
		{
			name:    "partial triplet",
			input:   `{"subject": "banana", "verb": "is", "object": "", "ambiguous": false}`,
			wantErr: false,
			check: func(r *QueryResult) {
				if r.Subject != "banana" {
					t.Errorf("Subject = %v, want banana", r.Subject)
				}
				if r.Object != "" {
					t.Errorf("Object = %v, want empty", r.Object)
				}
			},
		},
		{
			name:    "ambiguous query",
			input:   `{"subject": "python", "verb": "", "object": "", "ambiguous": true, "context": "programming"}`,
			wantErr: false,
			check: func(r *QueryResult) {
				if !r.Ambiguous {
					t.Error("Ambiguous should be true")
				}
				if r.Context != "programming" {
					t.Errorf("Context = %v, want programming", r.Context)
				}
			},
		},
		{
			name:    "invalid JSON",
			input:   `{"subject": "cat", "verb"}`,
			wantErr: true,
		},
		{
			name:    "empty object allowed",
			input:   `{"subject": "", "verb": "is", "object": "", "ambiguous": false}`,
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

