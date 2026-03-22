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
		fmt.Printf("Parsed: %d triplet(s)\n", len(queryResult.Triplets))
		for i, t := range queryResult.Triplets {
			fmt.Printf("  [%d] subject=%q, verb=%q, object=%q\n", i, t.Subject, t.Verb, t.Object)
		}

		// Step 2: Add user knowledge to KB first, then search for related knowledge
		var allTriplets []search.Triplet
		for _, triplet := range queryResult.Triplets {
			// Always add the user's triplet to KB first
			fmt.Printf("Adding to KB: %s %s %s\n", triplet.Subject, triplet.Verb, triplet.Object)
			newTriplet, err := generateNewKnowledge(inputClient, triplet, input)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error generating knowledge: %v\n", err)
				continue
			}
			if err := search.AddTriplet(*newTriplet, defsDir, itensDir); err != nil {
				continue
			}
			fmt.Println("User knowledge added!")

			// Include user's generated knowledge in the response (for greetings, statements, etc.)
			allTriplets = append(allTriplets, *newTriplet)

			// After adding, search for related knowledge
			// For questions, search for answers
			// For statements/greetings, search for related context (e.g., how to respond to greetings)
			if triplet.IsQuestion() {
				// User is asking - search the knowledge base
				fmt.Printf("Searching KB for: %s %s...\n", triplet.Subject, triplet.Verb)
				results, err := search.KnowledgeBase(defsDir, itensDir, search.Query{
					Subject:     triplet.Subject,
					Verb:        triplet.NormalizedVerb(),
					Object:      triplet.Object,
					Context:     triplet.Context,
					TemporalCtx: triplet.TemporalCtx,
				})
				if err != nil {
					fmt.Fprintf(os.Stderr, "Error searching: %v\n", err)
					continue
				}
				fmt.Printf("Found %d triplet(s)\n", len(results))
				allTriplets = append(allTriplets, results...)
			} else {
				// User is telling/saying something - search for related context
				// e.g., for greetings, find how to respond
				fmt.Printf("Searching KB for related context: %s %s...\n", triplet.Subject, triplet.Verb)
				results, err := search.KnowledgeBase(defsDir, itensDir, search.Query{
					Subject: triplet.Subject,
					Verb:   triplet.Verb,
					Object: triplet.Object,
				})
				if err != nil {
					fmt.Fprintf(os.Stderr, "Error searching: %v\n", err)
					continue
				}
				fmt.Printf("Found %d related triplet(s)\n", len(results))
				// Also search for related responses (e.g., how to respond to greetings)
				responseResults, err := search.KnowledgeBase(defsDir, itensDir, search.Query{
					Subject: "assistant",
					Verb:   "respond",
				})
				if err == nil && len(responseResults) > 0 {
					fmt.Printf("Found %d response triplet(s)\n", len(responseResults))
					allTriplets = append(allTriplets, responseResults...)
				}
				// Include user's own knowledge in response
				allTriplets = append(allTriplets, results...)
			}
		}

		// Step 3: Synthesize the response

		// Step 3: Synthesize the response
		fmt.Println("Synthesizing response...")
		response, err := synthesizeResponse(outputClient, allTriplets)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error synthesizing: %v\n", err)
			continue
		}

		fmt.Println("\nAnswer:")
		fmt.Println(response)

		// Step 4: Add the provider response to the KB (if there was a question)
		for _, triplet := range queryResult.Triplets {
			if triplet.IsQuestion() {
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
				break // Only add one response per interaction
			}
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

func generateNewKnowledge(client *llm.Client, triplet parse.Triplet, originalPrompt string) (*search.Triplet, error) {
	// Use defaults if parsed query is empty (e.g., for greetings)
	subject := triplet.Subject
	verb := triplet.Verb
	object := triplet.Object

	if subject == "" || verb == "" {
		// Default to user saying the original prompt
		subject = "user"
		verb = "say"
		object = originalPrompt
	}

	prompt := fmt.Sprintf(`Based on the statement "%s", generate a new knowledge triplet.

Statement: %s
Parsed triplet: subject=%q, verb=%q, object=%q

Provide a JSON triplet with: subject, verb, object, confidence (0.0-1.0), source, date (YYYY-MM-DD), and context.

Return ONLY the JSON triplet without any markdown formatting.`, originalPrompt, originalPrompt, subject, verb, object)

	messages := []llm.Message{
		{Role: "system", Content: `You are a knowledge base generator. Create accurate, factual triplets based on user statements. Always return ONLY valid JSON without markdown code blocks.`},
		{Role: "user", Content: prompt},
	}

	response, err := client.Chat(messages)
	if err != nil {
		return nil, err
	}

	// Strip markdown code blocks if present
	jsonStr := strings.TrimSpace(response)
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

	var knowledgeTriplet search.Triplet
	err = json.Unmarshal([]byte(jsonStr), &knowledgeTriplet)
	if err != nil {
		return nil, err
	}

	if knowledgeTriplet.Confidence == 0 {
		knowledgeTriplet.Confidence = 0.9
	}
	if knowledgeTriplet.Date == "" {
		knowledgeTriplet.Date = "2024-01-01"
	}
	if knowledgeTriplet.Source == "" {
		knowledgeTriplet.Source = "user"
	}
	knowledgeTriplet.Path = ""

	return &knowledgeTriplet, nil
}

func generateResponseKnowledge(client *llm.Client, queryResult *parse.QueryResult, response string) (*search.Triplet, error) {
	// Get context from the question triplets (if any)
	var subject, verb, object string
	for _, t := range queryResult.Triplets {
		if t.IsQuestion() {
			subject = t.Subject
			verb = t.NormalizedVerb()
			object = t.Object
			break
		}
	}

	// Default if no question found
	if subject == "" || verb == "" {
		subject = "assistant"
		verb = "respond"
		object = response
	}

	prompt := fmt.Sprintf(`Based on the response "%s", generate a knowledge triplet.

Response: %s
Original query subject: %q
Original query verb: %q
Original query object: %q

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

	// Try to parse as array first, then fall back to single object
	var triplets []search.Triplet
	err = json.Unmarshal([]byte(jsonStr), &triplets)
	if err != nil {
		// Try parsing as single triplet
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

	// Handle array of triplets - use the first one
	if len(triplets) == 0 {
		return nil, fmt.Errorf("no triplets found in response")
	}
	triplet := triplets[0]
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

