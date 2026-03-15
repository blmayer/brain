package config

import (
	"encoding/json"
	"os"
)

type Provider string

const (
	ProviderOpenAI   Provider = "openai"
	ProviderMistral  Provider = "mistral"
	ProviderAnthropic Provider = "anthropic"
)

type Model struct {
	Provider Provider `json:"provider"`
	Model    string    `json:"model"`
	APIKey   string    `json:"api_key,omitempty"`
}

type Config struct {
	Input  Model `json:"input"`
	Output Model `json:"output"`
}

func Load(path string) (*Config, error) {
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
		cfg.Input.APIKey = os.Getenv("OPENAI_API_KEY")
	}
	if cfg.Output.APIKey == "" {
		cfg.Output.APIKey = os.Getenv("OPENAI_API_KEY")
	}

	return &cfg, nil
}

