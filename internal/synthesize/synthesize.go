package synthesize

import (
	"brain/internal/search"
	"fmt"
)

// PlanNode represents a node in a plan graph.
// It contains a name and a list of dependencies.
// This structure is used to represent the steps and their dependencies
// in a program generation plan.
type PlanNode struct {
	Name    string
	Depends []PlanNode
}

// SystemPrompt returns the system prompt for the synthesizer
func SystemPrompt(triplets []search.Triplet) string {
	return fmt.Sprintf(`You are a knowledge synthesizer. Your task is to convert triplet data into a coherent natural language response.

Context:
- You have retrieved the following triplets from the knowledge base.
- Each triplet has: subject, verb, object, confidence, source, and date.
- Higher confidence means more certain information.
- Use the context to form a natural, informative answer.

Triplets:
%s

Instructions:
1. Form a coherent response from these facts.
2. Prioritize higher confidence information.
3. If confidence is below 0.5, note uncertainty.
4. Cite sources when available.
5. If the triplets indicate a greeting (user said hi, hello, etc.), respond with a friendly greeting.
6. If no triplets found, say "Hello! How can I help you today?" or a similar friendly greeting.
7. IMPORTANT: Respond ONLY using the information provided in the triplets. Do not hallucinate or add facts not present in the triplets.`, formatTriplets(triplets))
}

func formatTriplets(triplets []search.Triplet) string {
	if len(triplets) == 0 {
		return "(No triplets found)"
	}

	var s string
	for _, t := range triplets {
		// Include context if available
		ctx := ""
		if t.Context != "" {
			ctx = fmt.Sprintf(" (context: %s)", t.Context)
		}

		// Include temporal context if available
		temporal := ""
		if t.Date != "" {
			temporal = fmt.Sprintf(" [%s]", t.Date)
		}

		s += fmt.Sprintf("- %s %s %s (confidence: %.2f, source: %s, context: %s%s)%s\n",
			t.Subject, t.Verb, t.Object, t.Confidence, t.Source, t.Context, temporal, ctx)
	}
	return s
}

// CanAnswer checks if we have sufficient knowledge to answer
func CanAnswer(triplets []search.Triplet) bool {
	return len(triplets) > 0
}

// NeedsUpdate checks if we should ask for new knowledge
func NeedsUpdate(triplets []search.Triplet) bool {
	// If no triplets found, we need to update
	return len(triplets) == 0
}

// GeneratePlanForSumProgram generates a PlanNode structure for a program
// that reads two integers and prints their sum.
// This is a hardcoded implementation for testing purposes.
func GeneratePlanForSumProgram() PlanNode {
	// Create the 'a' node with its dependencies
	aNode := PlanNode{
		Name: "a",
		Depends: []PlanNode{
			{
				Name: "declaration",
				Depends: []PlanNode{{Name: "a"}},
			},
			{
				Name: "read",
				Depends: []PlanNode{{Name: "a"}},
			},
		},
	}

	// Create the 'b' node with its dependencies
	bNode := PlanNode{
		Name: "b",
		Depends: []PlanNode{
			{
				Name: "declaration",
				Depends: []PlanNode{{Name: "b"}},
			},
			{
				Name: "read",
				Depends: []PlanNode{{Name: "b"}},
			},
		},
	}

	// Create the 'sum' node with its dependencies
	sumNode := PlanNode{
		Name: "sum",
		Depends: []PlanNode{aNode, bNode},
	}

	// Create the 'print' node with its dependency
	printNode := PlanNode{
		Name: "print",
		Depends: []PlanNode{sumNode},
	}

	return printNode
}
