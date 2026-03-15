
package llm

import (
	"brain/internal/config"
	"testing"
)

func TestNewClient(t *testing.T) {
	tests := []struct {
		name   string
		model  config.Model
		want   string
	}{
		{
			name: "openai default",
			model: config.Model{
				Provider: config.ProviderOpenAI,
				Model:    "gpt-4",
				APIKey:   "test-key",
			},
			want: "https://api.openai.com/v1",
		},
		{
			name: "mistral",
			model: config.Model{
				Provider: config.ProviderMistral,
				Model:    "mistral-large",
				APIKey:   "test-key",
			},
			want: "https://api.mistral.ai/v1",
		},
		{
			name: "anthropic",
			model: config.Model{
				Provider: config.ProviderAnthropic,
				Model:    "claude-3",
				APIKey:   "test-key",
			},
			want: "https://api.openai.com/v1", // Falls back to OpenAI
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			client := NewClient(tt.model)
			if client.baseURL != tt.want {
				t.Errorf("NewClient() baseURL = %v, want %v", client.baseURL, tt.want)
			}
			if client.model != tt.model.Model {
				t.Errorf("NewClient() model = %v, want %v", client.model, tt.model.Model)
			}
			if client.apiKey != tt.model.APIKey {
				t.Errorf("NewClient() apiKey = %v, want %v", client.apiKey, tt.model.APIKey)
			}
		})
	}
}

func TestMessageAndRequestTypes(t *testing.T) {
	// Test that the types are properly defined
	msg := Message{
		Role:    "system",
		Content: "You are a helpful assistant.",
	}

	if msg.Role != "system" {
		t.Errorf("Message.Role = %v, want system", msg.Role)
	}

	req := Request{
		Model:    "gpt-4",
		Messages: []Message{msg},
	}

	if len(req.Messages) != 1 {
		t.Errorf("Request.Messages length = %v, want 1", len(req.Messages))
	}
}

