
package synthesize

import (
	"brain/internal/search"
	"fmt"
)

// SystemPrompt returns the system prompt for the synthesizer
func SystemPrompt(triplets []search.Triplet) string {
	return fmt.Sprintf(`You are a knowledge synthesizer. Your task is to convert triplet data into a coherent natural language response.

Context:
- You have retrieved the following triplets from the knowledge base
- Each triplet has: subject, verb, object, confidence, source, and date
- Higher confidence means more certain information
- Use the context to form a natural, informative answer

Triplets:
%s

Instructions:
1. Form a coherent response from these facts
2. Prioritize higher confidence information
3. If confidence is below 0.5, note uncertainty
4. Cite sources when available
5. If no triplets found, say "I don't have information about that."`, formatTriplets(triplets))
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
