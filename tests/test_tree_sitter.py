"""Tests for tree-sitter code chunking integration."""

import pytest

from stele.chunkers.code import CodeChunker, HAS_TREE_SITTER


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter not installed")
class TestTreeSitterChunking:
    """Tests for tree-sitter based code chunking."""

    def test_javascript_function_boundaries(self):
        chunker = CodeChunker(chunk_size=50)
        code = """
function hello(name) {
    console.log('Hello', name);
    console.log('World', name);
}

function goodbye(name) {
    console.log('Bye', name);
    console.log('See ya', name);
}

class Greeter {
    constructor(name) {
        this.name = name;
    }
    greet() {
        return this.name;
    }
}
"""
        chunks = chunker.chunk(code, "test.js")
        assert len(chunks) >= 2
        assert all(c.modality == "code" for c in chunks)
        assert all(c.metadata["language"] == "javascript" for c in chunks)

    def test_typescript_interfaces(self):
        chunker = CodeChunker(chunk_size=50)
        code = """
interface User {
    name: string;
    age: number;
    email: string;
}

type Status = 'active' | 'inactive' | 'pending';

function createUser(name: string): User {
    return { name, age: 0, email: '' };
}

class UserService {
    private users: User[] = [];
    add(user: User): void {
        this.users.push(user);
    }
}
"""
        chunks = chunker.chunk(code, "test.ts")
        assert len(chunks) >= 2
        full_content = "\n".join(c.content for c in chunks)
        assert "interface User" in full_content
        assert "type Status" in full_content
        assert "class UserService" in full_content

    def test_go_functions_and_types(self):
        chunker = CodeChunker(chunk_size=50)
        code = """package main

import "fmt"

func hello(name string) {
    fmt.Println("Hello", name)
}

type Greeter struct {
    Name string
    Count int
}

func (g *Greeter) Greet() string {
    g.Count++
    return "Hi " + g.Name
}

func main() {
    g := &Greeter{Name: "World"}
    fmt.Println(g.Greet())
}
"""
        chunks = chunker.chunk(code, "test.go")
        assert len(chunks) >= 2
        full = "\n".join(c.content for c in chunks)
        assert "func hello" in full
        assert "type Greeter" in full

    def test_rust_items(self):
        chunker = CodeChunker(chunk_size=50)
        code = """
use std::fmt;

pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }

    pub fn distance(&self, other: &Point) -> f64 {
        ((self.x - other.x).powi(2) + (self.y - other.y).powi(2)).sqrt()
    }
}

pub fn origin() -> Point {
    Point::new(0.0, 0.0)
}
"""
        chunks = chunker.chunk(code, "test.rs")
        assert len(chunks) >= 2
        full = "\n".join(c.content for c in chunks)
        assert "struct Point" in full
        assert "impl Point" in full

    def test_java_classes(self):
        chunker = CodeChunker(chunk_size=50)
        code = """
package com.example;

import java.util.List;

public class UserService {
    private List<String> users;

    public UserService() {
        this.users = new ArrayList<>();
    }

    public void addUser(String name) {
        users.add(name);
    }

    public int count() {
        return users.size();
    }
}
"""
        chunks = chunker.chunk(code, "test.java")
        assert len(chunks) >= 1
        assert any("class UserService" in c.content for c in chunks)

    def test_c_functions(self):
        chunker = CodeChunker(chunk_size=50)
        code = """
#include <stdio.h>
#include <stdlib.h>

typedef struct {
    int x;
    int y;
} Point;

void print_point(Point* p) {
    printf("(%d, %d)\\n", p->x, p->y);
}

int add(int a, int b) {
    return a + b;
}

int main(int argc, char** argv) {
    Point p = {1, 2};
    print_point(&p);
    return 0;
}
"""
        chunks = chunker.chunk(code, "test.c")
        assert len(chunks) >= 2
        full = "\n".join(c.content for c in chunks)
        assert "print_point" in full

    def test_large_file_splits_correctly(self):
        """Ensure tree-sitter produces multiple chunks for large files."""
        chunker = CodeChunker(chunk_size=100)
        functions = []
        for i in range(20):
            functions.append(
                f"function fn_{i}(x) {{\n"
                f"    console.log('fn_{i}', x);\n"
                f"    console.log('more output');\n"
                f"    return x + {i};\n"
                f"}}\n"
            )
        code = "\n".join(functions)
        chunks = chunker.chunk(code, "large.js")
        assert len(chunks) >= 3

    def test_empty_file(self):
        chunker = CodeChunker()
        chunks = chunker.chunk("", "empty.js")
        assert len(chunks) == 1
        assert chunks[0].content == ""

    def test_no_definitions(self):
        """File with no recognizable definitions falls back to regex/lines."""
        chunker = CodeChunker()
        code = "// just a comment\nconst x = 42;\n"
        chunks = chunker.chunk(code, "simple.js")
        assert len(chunks) >= 1
        assert chunks[0].content.strip() != ""


class TestRegexFallback:
    """Tests that regex fallback still works when tree-sitter is absent."""

    def test_js_regex_chunking(self):
        """Regex path produces reasonable chunks for JS."""
        chunker = CodeChunker(chunk_size=50)
        code = """
function hello() {
    console.log('hello');
}

class Foo {
    bar() { return 1; }
}
"""
        # Force regex path -- now uses _boundaries_to_chunks so small code
        # may merge into fewer chunks based on chunk_size
        chunks = chunker._chunk_regex(code, "test.js", "js")
        assert len(chunks) >= 1
        assert all(c.metadata["language"] == "js" for c in chunks)
        # With very small chunk_size, multiple definitions should split
        chunker_small = CodeChunker(chunk_size=10)
        chunks_small = chunker_small._chunk_regex(code, "test.js", "js")
        assert len(chunks_small) >= 2

    def test_python_always_uses_ast(self):
        """Python should always use stdlib ast, never tree-sitter."""
        chunker = CodeChunker()
        code = "def foo():\n    return 1\n\nclass Bar:\n    pass\n"
        chunks = chunker.chunk(code, "test.py")
        assert len(chunks) >= 1
        assert chunks[0].metadata["language"] == "python"
