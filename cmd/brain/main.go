package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
)

type NodeID string

type EmitNode interface {
	isEmitNode()
}

type EmitNodeType string

const (
	TextNodeType EmitNodeType = "TextNode"
	RefNodeType  EmitNodeType = "RefNode"
)

type RefNode struct{ Ref string }

func (RefNode) isEmitNode() {}

type TextNode struct{ Text string }

func (TextNode) isEmitNode() {}

type Node struct {
	ID         NodeID
	Depends    []struct {
		Name string `json:"Name"`
		Type string `json:"Type"`
	}
	Produces   []struct {
		Name string `json:"Name"`
		Type string `json:"Type"`
	}
	Emits      []EmitNode
	Context    string
	Confidence float64
	Source     string
	Date       string
}

func (n *Node) UnmarshalJSON(data []byte) error {
	type Alias Node
	aux := &struct {
		Emits []struct {
			Type  string `json:"Type"`
			Value string `json:"Value"`
		} `json:"Emits"`
		*Alias
	}{
		Alias: (*Alias)(n),
	}

	if err := json.Unmarshal(data, &aux); err != nil {
		return err
	}

	// Convert Emits
	n.Emits = make([]EmitNode, len(aux.Emits))
	for i, emit := range aux.Emits {
		switch emit.Type {
		case "TextNode":
			n.Emits[i] = TextNode{Text: emit.Value}
		case "RefNode":
			n.Emits[i] = RefNode{Ref: emit.Value}
		}
	}

	return nil
}

var nodeDB = map[NodeID]Node{}

type Symbol struct {
	Name string
	Type string
}

type Context struct {
	Bindings map[string]Symbol
	Counter  int
}

func (ctx *Context) Bind(name, typ string) Symbol {
	if sym, ok := ctx.Bindings[name]; ok {
		return sym
	}
	ctx.Counter++
	sym := Symbol{
		Name: fmt.Sprintf("%s%d", typ, ctx.Counter),
		Type: typ,
	}
	ctx.Bindings[name] = sym
	return sym
}

type ExecNode struct {
	Node     Node
	Bindings map[string]Symbol
	Deps     []*ExecNode
}

// --- Plan tree (input structure) ---
type PlanNode struct {
	ID       NodeID
	Children []*PlanNode
}

// --- Solver ---
func SolvePlan(plan *PlanNode, ctx *Context) *ExecNode {
	node := nodeDB[plan.ID]

	exec := &ExecNode{
		Node:     node,
		Bindings: make(map[string]Symbol),
	}

	// First solve children (important!)
	for _, child := range plan.Children {
		childExec := SolvePlan(child, ctx)
		exec.Deps = append(exec.Deps, childExec)
	}

	// Resolve dependencies
	for _, req := range node.Depends {
		sym, exists := ctx.Bindings[req.Name]
		if !exists {
			// create variable binding
			sym = ctx.Bind(req.Name, req.Type)
		}
		exec.Bindings[req.Name] = sym
		
		// Solve the dependency node itself
		if _, exists := nodeDB[NodeID(req.Name)]; exists {
			depExec := SolvePlan(&PlanNode{ID: NodeID(req.Name)}, ctx)
			exec.Deps = append(exec.Deps, depExec)
		}
	}

	// Produce outputs
	for _, prod := range node.Produces {
		sym := ctx.Bind(prod.Name, prod.Type)
		exec.Bindings[prod.Name] = sym
	}

	return exec
}

// --- Render ---
func Render(node Node, bindings map[string]Symbol) string {
	var out strings.Builder
	for _, e := range node.Emits {
		switch v := e.(type) {
		case TextNode:
			out.WriteString(v.Text)
		case RefNode:
			out.WriteString(bindings[v.Ref].Name)
		}
	}
	return out.String()
}

// --- Emit (DFS) ---
func Emit(exec *ExecNode, visited map[string]bool, out *[]string) {
	key := makeKey(exec)
	if visited[key] {
		return
	}
	visited[key] = true

	for _, dep := range exec.Deps {
		Emit(dep, visited, out)
	}

	line := Render(exec.Node, exec.Bindings)
	if line != "" {
		*out = append(*out, line)
	}
}

func makeKey(e *ExecNode) string {
	key := string(e.Node.ID)
	for k, v := range e.Bindings {
		key += "|" + k + "=" + v.Name
	}
	return key
}

func LoadNodeDB(dir string) error {
	return filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() || filepath.Ext(path) != ".json" {
			return nil
		}

		data, err := os.ReadFile(path)
		if err != nil {
			return nil // Skip unreadable files
		}

		var node Node
		if err := json.Unmarshal(data, &node); err != nil {
			return nil // Skip invalid JSON
		}

		nodeDB[node.ID] = node
		return nil
	})
}

func main() {
	// Load nodeDB from knowledge files
	if err := LoadNodeDB("kb/programming_languages/go"); err != nil {
		log.Fatalf("Failed to load nodeDB: %v", err)
	}

	ctx := &Context{
		Bindings: make(map[string]Symbol),
	}

	// Correct structured input
	plan := &PlanNode{
		ID: "print",
		Children: []*PlanNode{
			{
				ID: "sum",
			},
		},
	}

	root := SolvePlan(plan, ctx)

	var lines []string
	visited := make(map[string]bool)

	Emit(root, visited, &lines)

	// Output the generated Go program
	fmt.Println("package main")
	fmt.Println(`import "fmt"`)
	fmt.Println("\nfunc main() {")
	for _, l := range lines {
		fmt.Println("  " + l)
	}
	fmt.Println("}")
}
