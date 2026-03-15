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
	// Default paths
	configPath := "config.json"
	rootDir := "."

	// Allow command line overrides
	if len(os.Args) > 1 {
		rootDir = os.Args[1]
	}
	if len(os.Args) > 2 {
		configPath = os.Args[2]
	}

	// Load config
	cfg, err := config.Load(configPath)
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

		// Step 3a: Check if we need to add new knowledge
		if synthesize.NeedsUpdate(triplets) {
			fmt.Println("No knowledge found. Generating new knowledge...")

			// Ask LLM to generate new knowledge
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

			fmt.Println("New knowledge added!")

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
		}

		// Step 3b: Synthesize the response
		// Step 3b: Synthesize the response
		fmt.Println("Synthesizing response...")
		response, err := synthesizeResponse(outputClient, triplets)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error synthesizing: %v\n", err)
			continue
		}

		fmt.Println("\nAnswer:")
		fmt.Println(response)

		fmt.Print("\nWould you like to add more information? (yes/no): ")
		addMore, _ := reader.ReadString('\n')
		addMore = strings.TrimSpace(strings.ToLower(addMore))
		if addMore == "yes" {
			fmt.Print("What would you like to add? ")
			additionalInfo, _ := reader.ReadString('\n')
			additionalInfo = strings.TrimSpace(additionalInfo)

			newTriplet, err := incorporateAdditionalKnowledge(inputClient, queryResult, additionalInfo)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error incorporating knowledge: %v\n", err)
				continue
			}

			if err := search.AddTriplet(*newTriplet, defsDir, itensDir); err != nil {
				fmt.Fprintf(os.Stderr, "Error adding knowledge: %v\n", err)
				continue
			}
			fmt.Println("Additional knowledge added!")
		}
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
	prompt := fmt.Sprintf(`Based on the question "%s", generate a new knowledge triplet.

Question: %s
Parsed query: subject=%q, verb=%q, object=%q

Provide a JSON triplet with: subject, verb, object, confidence (0.0-1.0), source, date (YYYY-MM-DD), and context.

Return ONLY the JSON triplet.`, originalPrompt, originalPrompt, queryResult.Subject, queryResult.Verb, queryResult.Object)

	messages := []llm.Message{
		{Role: "system", Content: `You are a knowledge base generator. Create accurate, factual triplets based on user questions.`},
		{Role: "user", Content: prompt},
	}

	response, err := client.Chat(messages)
	if err != nil {
		return nil, err
	}

	var triplet search.Triplet
	err = json.Unmarshal([]byte(response), &triplet)
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
		triplet.Source = "generated from user query"
	}
	triplet.Path = ""

	return &triplet, nil
}

func incorporateAdditionalKnowledge(client *llm.Client, queryResult *parse.QueryResult, additionalInfo string) (*search.Triplet, error) {
	prompt := fmt.Sprintf(`The user wants to add more information: "%s".

Original question: %s
Parsed query: subject=%q, verb=%q, object=%q

Provide a JSON triplet with: subject, verb, object, confidence (0.0-1.0), source, date (YYYY-MM-DD), and context.

Return ONLY the JSON triplet.`, additionalInfo, queryResult.Subject, queryResult.Verb, queryResult.Object)

	messages := []llm.Message{
		{Role: "system", Content: `You are a knowledge base updater. Create accurate triplets based on user-provided information.`},
		{Role: "user", Content: prompt},
	}

	response, err := client.Chat(messages)
	if err != nil {
		return nil, err
	}

	var triplet search.Triplet
	err = json.Unmarshal([]byte(response), &triplet)
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
		triplet.Source = "user-provided"
	}
	triplet.Path = ""

	return &triplet, nil
}

func printJSON(v interface{}) {
	data, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(data))
}
