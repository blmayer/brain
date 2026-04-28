package main

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"brain/internal/config"
	"brain/internal/llm"
	"brain/internal/search"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: brain <directory>")
		os.Exit(1)
	}

	projectPath := os.Args[len(os.Args)-1]

    if _, err := os.Stat(filepath.Join(projectPath, ".brain/memory.json")); err != nil {
        log.Printf("Brain not found at: %s", projectPath)
        fmt.Println("Please run brain from or in a Brain project directory.")
        os.Exit(1)
    }

    cfg, err := config.Load(filepath.Join(projectPath, ".brain/config.json"))
    if err != nil {
        log.Fatalf("Failed to load config: %v", err)
    }

    search.InitMemoryKB(filepath.Join(projectPath, "kb"))
    client := llm.NewClient(cfg.Input)

    reader := bufio.NewReader(os.Stdin)

    fmt.Printf("\nBrain - Query system.\n> ")

    for {
        text, err := reader.ReadString('\n')
        if err != nil {
            log.Printf("Error reading input: %v", err)
            continue
        }
        text = strings.TrimSpace(text)

        if strings.HasPrefix(text, "/q ") {
            answer, err := client.Chat([]llm.Message{
                {Role: "system", Content: "You are a helpful thinking assistant."},
                {Role: "user", Content: text[3:]},
            })
            if err != nil {
                log.Printf("Error getting LLM response: %v", err)
                continue
            }
            fmt.Println(answer)
        } else {
            fmt.Print("  ")
        }
    }
}


