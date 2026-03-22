package llm

import (
	"brain/internal/config"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type Request struct {
	Model    string          `json:"model"`
	Messages []Message       `json:"messages"`
}
type Response struct {
	Choices []Choice `json:"choices"`
}

type Choice struct {
	Message Message `json:"message"`
}

// Client wraps HTTP calls to LLM providers
type Client struct {
	provider config.Provider
	model    string
	groupId  string
	apiKey   string
	baseURL  string
	options  map[string]any
}

func NewClient(model config.Model) *Client {
	baseURL := "https://api.openai.com/v1"
	if model.Provider == config.ProviderMistral {
		baseURL = "https://api.mistral.ai/v1"
	}
	if model.Provider == config.ProviderMinimax {
		baseURL = "https://api.minimax.io/v1"
	}

	return &Client{
		provider: model.Provider,
		model:    model.Model,
		apiKey:   model.APIKey,
		baseURL:  baseURL,
		options:  model.Options,
	}
}

// getLogFilePath returns the path to the log file in the XDG cache directory
func getLogFilePath() (string, error) {
	// Get XDG_CACHE_HOME, default to ~/.cache
	cacheHome := os.Getenv("XDG_CACHE_HOME")
	if cacheHome == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		cacheHome = filepath.Join(home, ".cache")
	}

	// Create brain cache directory if it doesn't exist
	cacheDir := filepath.Join(cacheHome, "brain")
	if err := os.MkdirAll(cacheDir, 0755); err != nil {
		return "", err
	}

	return filepath.Join(cacheDir, "requests.log"), nil
}

// logToFile writes a log message to the log file in XDG cache directory
func logToFile(format string, args ...interface{}) {
	logPath, err := getLogFilePath()
	if err != nil {
		log.Printf("Failed to get log file path: %v", err)
		return
	}

	msg := fmt.Sprintf(format, args...)
	logEntry := fmt.Sprintf("[%s] %s\n", time.Now().Format(time.RFC3339), msg)

	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("Failed to open log file: %v", err)
		return
	}
	defer f.Close()

	if _, err := f.WriteString(logEntry); err != nil {
		log.Printf("Failed to write to log file: %v", err)
	}
}

func (c *Client) Chat(messages []Message) (string, error) {
	opts := c.options
	if opts == nil {
		opts = make(map[string]any)
	}

	// Merge options into request for JSON marshaling
	reqMap := map[string]any{
		"model":    c.model,
		"messages": messages,
	}
	for k, v := range opts {
		reqMap[k] = v
	}

	body, err := json.Marshal(reqMap)
	if err != nil {
		return "", err
	}

	httpReq, err := http.NewRequest("POST", c.baseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return "", err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)

	// Log the request to the provider
	logToFile("REQUEST | Provider: %s | Model: %s | Messages: %s",
		c.provider, c.model, messagesToString(messages))

	client := &http.Client{}
	resp, err := client.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	// Log the response from the provider
	var prettyJSON bytes.Buffer
	if err := json.Indent(&prettyJSON, data, "", "  "); err == nil {
		logToFile("RESPONSE | Provider: %s | Status: %d | Body:\n%s",
			c.provider, resp.StatusCode, prettyJSON.String())
	} else {
		logToFile("RESPONSE | Provider: %s | Status: %d | Body: %s",
			c.provider, resp.StatusCode, string(data))
	}

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("API error: %s", string(data))
	}

	var result Response
	if err := json.Unmarshal(data, &result); err != nil {
		return "", err
	}

	if len(result.Choices) == 0 {
		return "", fmt.Errorf("no response from LLM")
	}

	// Log the parsed response content for easier reading
	content := result.Choices[0].Message.Content
	logToFile("RESPONSE CONTENT | Provider: %s | Content: %s",
		c.provider, content)

	return content, nil
}

// messagesToString converts messages to a string representation for logging
func messagesToString(messages []Message) string {
	var result string
	for i, msg := range messages {
		if i > 0 {
			result += " | "
		}
		result += fmt.Sprintf("[%s]: %s", msg.Role, msg.Content)
	}
	return result
}

