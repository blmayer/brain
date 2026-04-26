package main

import (
	"fmt"
	"strings"
)

type NodeID string

type Requirement struct {
	Name string
	Type string
}

type EmitNode interface {
	isEmitNode()
}

type TextNode struct{ Text string }
func (TextNode) isEmitNode() {}

type RefNode struct{ Ref string }
func (RefNode) isEmitNode() {}

type Node struct {
	ID       NodeID
	Depends  []Requirement
	Produces []Requirement
	Emits    []EmitNode
}

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

// --- Node DB ---

var nodeDB = map[NodeID]Node{

	"declare_int": {
		ID: "declare_int",
		Produces: []Requirement{
			{Name: "var", Type: "int"},
		},
		Emits: []EmitNode{
			TextNode{"var "}, RefNode{"var"}, TextNode{" int"},
		},
	},

	"read_int": {
		ID: "read_int",
		Depends: []Requirement{
			{Name: "var", Type: "int"},
		},
		Emits: []EmitNode{
			TextNode{`fmt.Scanf("%d", &`}, RefNode{"var"}, TextNode{")"},
		},
	},

	"calculate_sum": {
		ID: "calculate_sum",
		Depends: []Requirement{
			{Name: "var_a", Type: "int"},
			{Name: "var_b", Type: "int"},
		},
		Produces: []Requirement{
			{Name: "result", Type: "int"},
		},
		Emits: []EmitNode{
			RefNode{"result"}, TextNode{" := "},
			RefNode{"var_a"}, TextNode{" + "}, RefNode{"var_b"},
		},
	},

	"print_result": {
		ID: "print_result",
		Depends: []Requirement{
			{Name: "result", Type: "int"},
		},
		Emits: []EmitNode{
			TextNode{"fmt.Println("}, RefNode{"result"}, TextNode{")"},
		},
	},
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
			// create variable
			sym = ctx.Bind(req.Name, req.Type)

			// declare + read
			decl := &ExecNode{
				Node: nodeDB["declare_int"],
				Bindings: map[string]Symbol{
					"var": sym,
				},
			}

			read := &ExecNode{
				Node: nodeDB["read_int"],
				Bindings: map[string]Symbol{
					"var": sym,
				},
			}

			exec.Deps = append(exec.Deps, decl, read)
		}

		exec.Bindings[req.Name] = sym
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

// --- Main ---

func main() {

	ctx := &Context{
		Bindings: make(map[string]Symbol),
	}

	// ✅ Correct structured input
	plan := &PlanNode{
		ID: "print_result",
		Children: []*PlanNode{
			{
				ID: "calculate_sum",
			},
		},
	}

	root := SolvePlan(plan, ctx)

	var lines []string
	visited := make(map[string]bool)

	Emit(root, visited, &lines)

	// --- valid_go_program ---

	fmt.Println("package main")
	fmt.Println(`import "fmt"`)

	fmt.Println("\nfunc main() {")
	for _, l := range lines {
		fmt.Println("  " + l)
	}
	fmt.Println("}")
}
