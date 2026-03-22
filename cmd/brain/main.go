package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"brain/internal/config"
	"brain/internal/llm"
	"brain/internal/parse"
	"brain/internal/search"
	"brain/internal/synthesize"
)

func main() {
	// Default root directory
	rootDir := "."

	// Allow command line override for root directory
	if len(os.Args) > 1 {
		rootDir = os.Args[1]
	}

	// Load config (XDG-compliant, searches in standard locations)
	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading config: %v\n", err)
		os.Exit(1)
	}

	// Create LLM clients
	inputClient := llm.NewClient(cfg.Input)
	outputClient := llm.NewClient(cfg.Output)

	// Determine paths
	defsDir := filepath.Join(rootDir, "defs")
	itensDir := filepath.Join(rootDir, "itens")

	// Ensure directories exist
	for _, dir := range []string{defsDir, itensDir} {
		if _, err := os.Stat(dir); os.IsNotExist(err) {
			fmt.Fprintf(os.Stderr, "Directory not found: %s\n", dir)
			os.Exit(1)
		}
	}

	// Interactive mode
	reader := bufio.NewReader(os.Stdin)
	fmt.Println("Brain - Knowledge Base System")
	fmt.Println("-------------------------------")
	fmt.Println("Ask me anything (type 'quit' to exit):")

	for {
		fmt.Print("\n> ")
		input, err := reader.ReadString('\n')
		if err != nil {
			break
		}
		input = strings.TrimSpace(input)

		if input == "quit" || input == "exit" {
			break
		}

		if input == "" {
			continue
		}

		// Step 1: Parse the query using LLM
		fmt.Println("Parsing query...")
		queryResult, err := parseQuery(inputClient, input)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error parsing query: %v\n", err)
			continue
		}

		// Debug: show parsed query
		fmt.Printf("Parsed: subject=%q, verb=%q, object=%q\n",
			queryResult.Subject, queryResult.Verb, queryResult.Object)

		// Step 2: Search the knowledge base with context and temporal awareness
		fmt.Println("Searching knowledge base...")
		triplets, err := search.KnowledgeBase(defsDir, itensDir, search.Query{
			Subject:     queryResult.Subject,
			Verb:        queryResult.Verb,
			Object:      queryResult.Object,
			Context:     queryResult.Context,
			TemporalCtx: queryResult.TemporalCtx,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error searching: %v\n", err)
			continue
		}

		fmt.Printf("Found %d triplet(s)\n", len(triplets))

		// Step 3a: Generate and add new knowledge from user input
		fmt.Println("Generating knowledge from user input...")

		// Ask LLM to generate new knowledge from user's question
		newTriplet, err := generateNewKnowledge(inputClient, queryResult, input)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error generating knowledge: %v\n", err)
			continue
		}

		// Add the new knowledge to the KB
		if err := search.AddTriplet(*newTriplet, defsDir, itensDir); err != nil {
			fmt.Fprintf(os.Stderr, "Error adding knowledge: %v\n", err)
			continue
		}

		fmt.Println("User knowledge added!")

		// Now search again with the updated KB
		triplets, err = search.KnowledgeBase(defsDir, itensDir, search.Query{
			Subject:     queryResult.Subject,
			Verb:        queryResult.Verb,
			Object:      queryResult.Object,
			Context:     queryResult.Context,
			TemporalCtx: queryResult.TemporalCtx,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error searching: %v\n", err)
			continue
		}


		// Step 3b: Synthesize the response
		fmt.Println("Synthesizing response...")
		response, err := synthesizeResponse(outputClient, triplets)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error synthesizing: %v\n", err)
			continue
		}

		fmt.Println("\nAnswer:")
		fmt.Println(response)

		// Step 3c: Add the provider response to the KB
		fmt.Println("Adding provider response to knowledge base...")
		responseTriplet, err := generateResponseKnowledge(inputClient, queryResult, response)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating response knowledge: %v\n", err)
			continue
		}

		if err := search.AddTriplet(*responseTriplet, defsDir, itensDir); err != nil {
			fmt.Fprintf(os.Stderr, "Error adding response knowledge: %v\n", err)
			continue
		}
		fmt.Println("Provider response added to knowledge base!")
		fmt.Println("\n---")
	}


}
func parseQuery(client *llm.Client, prompt string) (*parse.QueryResult, error) {
	messages := []llm.Message{
		{Role: "system", Content: parse.SystemPrompt()},
		{Role: "user", Content: prompt},
	}

	response, err := client.Chat(messages)
	if err != nil {
		return nil, err
	}

	return parse.ParseResult(response)
}

func synthesizeResponse(client *llm.Client, triplets []search.Triplet) (string, error) {
	messages := []llm.Message{
		{Role: "system", Content: synthesize.SystemPrompt(triplets)},
		{Role: "user", Content: "Please provide a natural language answer based on these triplets."},
	}

	return client.Chat(messages)
}

func generateNewKnowledge(client *llm.Client, queryResult *parse.QueryResult, originalPrompt string) (*search.Triplet, error) {
	// Use defaults if parsed query is empty (e.g., for greetings)
	subject := queryResult.Subject
	verb := queryResult.Verb
	object := queryResult.Object

	if subject == "" || verb == "" || object == "" {
		// Default to user saying the original prompt
		subject = "user"
		verb = "say"
		object = originalPrompt
	}

	prompt := fmt.Sprintf(`Based on the question "%s", generate a new knowledge triplet.

Question: %s
Parsed query: subject=%q, verb=%q, object=%q

Provide a JSON triplet with: subject, verb, object, confidence (0.0-1.0), source, date (YYYY-MM-DD), and context.

Return ONLY the JSON triplet without any markdown formatting.`, originalPrompt, originalPrompt, subject, verb, object)

	messages := []llm.Message{
		{Role: "system", Content: `You are a knowledge base generator. Create accurate, factual triplets based on user questions. Always return ONLY valid JSON without markdown code blocks.`},
		{Role: "user", Content: prompt},
	}

	response, err := client.Chat(messages)
	if err != nil {
		return nil, err
	}

	// Strip markdown code blocks if present
	jsonStr := strings.TrimSpace(response)
	// Remove opening ```json or ```
	for {
		if strings.HasPrefix(jsonStr, "```json") {
			jsonStr = strings.TrimPrefix(jsonStr, "```json")
		} else if strings.HasPrefix(jsonStr, "```") {
			jsonStr = strings.TrimPrefix(jsonStr, "```")
		} else {
			break
		}
	}
	// Remove trailing ```
	for {
		if strings.HasSuffix(jsonStr, "```") {
			jsonStr = strings.TrimSuffix(jsonStr, "```")
		} else {
			break
		}
	}
	jsonStr = strings.TrimSpace(jsonStr)

	var triplet search.Triplet
	err = json.Unmarshal([]byte(jsonStr), &triplet)
	if err != nil {
		return nil, err
	}

	if triplet.Confidence == 0 {
		triplet.Confidence = 0.9
	}
	if triplet.Date == "" {
		triplet.Date = "2024-01-01"
	}
	if triplet.Source == "" {
		triplet.Source = "user"
	}
	triplet.Path = ""

	return &triplet, nil
}

func generateResponseKnowledge(client *llm.Client, queryResult *parse.QueryResult, response string) (*search.Triplet, error) {
	// Use the original query context
	subject := queryResult.Subject
	verb := queryResult.Verb
	object := queryResult.Object

	// Default if query is empty
	if subject == "" || verb == "" || object == "" {
		subject = "assistant"
		verb = "respond"
		object = response
	}

	prompt := fmt.Sprintf(`Based on the response "%s", generate a knowledge triplet.

Response: %s
Original query: subject=%q, verb=%q, object=%q

Provide a JSON triplet with: subject, verb, object, confidence (0.0-1.0), source, date (YYYY-MM-DD), and context.

Return ONLY the JSON triplet without any markdown formatting.`, response, response, subject, verb, object)

	messages := []llm.Message{
		{Role: "system", Content: `You are a knowledge base generator. Create accurate, factual triplets based on responses. Always return ONLY valid JSON without markdown code blocks.`},
		{Role: "user", Content: prompt},
	}

	responseContent, err := client.Chat(messages)
	if err != nil {
		return nil, err
	}

	// Strip markdown code blocks if present
	jsonStr := strings.TrimSpace(responseContent)
	for {
		if strings.HasPrefix(jsonStr, "```json") {
			jsonStr = strings.TrimPrefix(jsonStr, "```json")
		} else if strings.HasPrefix(jsonStr, "```") {
			jsonStr = strings.TrimPrefix(jsonStr, "```")
		} else {
			break
		}
	}
	for {
		if strings.HasSuffix(jsonStr, "```") {
			jsonStr = strings.TrimSuffix(jsonStr, "```")
		} else {
			break
		}
	}
	jsonStr = strings.TrimSpace(jsonStr)

	var triplet search.Triplet
	err = json.Unmarshal([]byte(jsonStr), &triplet)
	if err != nil {
		return nil, err
	}

	if triplet.Confidence == 0 {
		triplet.Confidence = 0.95
	}
	if triplet.Date == "" {
		triplet.Date = "2024-01-01"
	}
	if triplet.Source == "" {
		triplet.Source = "provider response"
	}
	triplet.Path = ""

	return &triplet, nil
}

