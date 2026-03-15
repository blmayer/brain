
package llm

import (
	"brain/internal/config"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type Request struct {
	Model    string    `json:"model"`
	Messages []Message `json:"messages"`
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
	apiKey   string
	baseURL  string
}

func NewClient(model config.Model) *Client {
	baseURL := "https://api.openai.com/v1"
	if model.Provider == config.ProviderMistral {
		baseURL = "https://api.mistral.ai/v1"
	}
	// Add other providers as needed

	return &Client{
		provider: model.Provider,
		model:    model.Model,
		apiKey:   model.APIKey,
		baseURL:  baseURL,
	}
}

func (c *Client) Chat(messages []Message) (string, error) {
	req := Request{
		Model:    c.model,
		Messages: messages,
	}

	body, err := json.Marshal(req)
	if err != nil {
		return "", err
	}

	httpReq, err := http.NewRequest("POST", c.baseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return "", err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)

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

	return result.Choices[0].Message.Content, nil
}

