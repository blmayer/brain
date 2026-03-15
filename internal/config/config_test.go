
package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoad(t *testing.T) {
	// Create a temporary config file
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.json")

	configContent := `{
		"input": {
			"provider": "openai",
			"model": "gpt-4",
			"api_key": "test-key"
		},
		"output": {
			"provider": "mistral",
			"model": "mistral-large",
			"api_key": ""
		}
	}`

	err := os.WriteFile(configPath, []byte(configContent), 0644)
	if err != nil {
		t.Fatalf("failed to write temp config: %v", err)
	}

	// Test loading with API key in file
	cfg, err := Load(configPath)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Input.Provider != ProviderOpenAI {
		t.Errorf("Input.Provider = %v, want %v", cfg.Input.Provider, ProviderOpenAI)
	}
	if cfg.Input.Model != "gpt-4" {
		t.Errorf("Input.Model = %v, want gpt-4", cfg.Input.Model)
	}
	if cfg.Input.APIKey != "test-key" {
		t.Errorf("Input.APIKey = %v, want test-key", cfg.Input.APIKey)
	}

	if cfg.Output.Provider != ProviderMistral {
		t.Errorf("Output.Provider = %v, want %v", cfg.Output.Provider, ProviderMistral)
	}
}

func TestLoadEnvVarOverride(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.json")

	configContent := `{
		"input": {
			"provider": "openai",
			"model": "gpt-4",
			"api_key": ""
		},
		"output": {
			"provider": "openai",
			"model": "gpt-4"
		}
	}`

	err := os.WriteFile(configPath, []byte(configContent), 0644)
	if err != nil {
		t.Fatalf("failed to write temp config: %v", err)
	}

	// Set environment variable
	os.Setenv("OPENAI_API_KEY", "env-api-key")
	defer os.Unsetenv("OPENAI_API_KEY")

	cfg, err := Load(configPath)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Input.APIKey != "env-api-key" {
		t.Errorf("Input.APIKey = %v, want env-api-key", cfg.Input.APIKey)
	}
	if cfg.Output.APIKey != "env-api-key" {
		t.Errorf("Output.APIKey = %v, want env-api-key", cfg.Output.APIKey)
	}
}

func TestLoadFileNotFound(t *testing.T) {
	_, err := Load("nonexistent.json")
	if err == nil {
		t.Error("Load() expected error for nonexistent file")
	}
}

func TestLoadInvalidJSON(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.json")

	os.WriteFile(configPath, []byte("invalid json"), 0644)

	_, err := Load(configPath)
	if err == nil {
		t.Error("Load() expected error for invalid JSON")
	}
}

