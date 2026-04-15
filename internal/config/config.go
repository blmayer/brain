package config

import (
	"encoding/json"
	"os"
	"path/filepath"
)

type Provider string

const (
	ProviderOpenAI    Provider = "openai"
	ProviderMistral   Provider = "mistral"
	ProviderAnthropic Provider = "anthropic"
	ProviderMinimax   Provider = "minimax"
	ProviderOllama    Provider = "ollama"
)

type Model struct {
	Provider Provider                 `json:"provider"`
	Model    string                   `json:"model"`
	APIKey   string                   `json:"api_key,omitempty"`
	Options  map[string]interface{}   `json:"options,omitempty"`
}

type Config struct {
	Input  Model `json:"input"`
	Output Model `json:"output"`
}

// Load returns a Config, searching in XDG-compliant locations.
// If path is non-empty, it will be used directly.
// Otherwise, it checks: $XDG_CONFIG_HOME/brain/config.json, then ~/.config/brain/config.json,
// then falls back to ./config.json in the current directory.
func Load() (*Config, error) {
	// Try XDG_CONFIG_HOME (default: ~/.config)
	configHome := os.Getenv("XDG_CONFIG_HOME")
	if configHome == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, err
		}
		configHome = filepath.Join(home, ".config")
	}

	// Check XDG config path: $XDG_CONFIG_HOME/brain/config.json
	xdgPath := filepath.Join(configHome, "brain", "config.json")
	if _, err := os.Stat(xdgPath); err == nil {
		return loadFromPath(xdgPath)
	}

	// Fall back to ./config.json in current directory
	return loadFromPath("config.json")
}

func loadFromPath(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}

	// Load API key from env if not in config
	if cfg.Input.APIKey == "" {
		switch cfg.Input.Provider {
		case ProviderMinimax:
			cfg.Input.APIKey = os.Getenv("MINIMAX_API_KEY")
		default:
			cfg.Input.APIKey = os.Getenv("OPENAI_API_KEY")
		}
	}
	if cfg.Output.APIKey == "" {
		switch cfg.Output.Provider {
		case ProviderMinimax:
			cfg.Output.APIKey = os.Getenv("MINIMAX_API_KEY")
		default:
			cfg.Output.APIKey = os.Getenv("OPENAI_API_KEY")
		}
	}

	return &cfg, nil
}


