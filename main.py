import sqlite3
import os
from pathlib import Path
from datetime import datetime
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from PyPDF2 import PdfReader

app = typer.Typer(help="Fast local document search and indexing CLI tool")
console = Console()

DB_PATH = Path.home() / ".doc_finder.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            filetype TEXT NOT NULL,
            content TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def read_file_content(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    
    if ext == ".pdf":
        try:
            reader = PdfReader(str(filepath))
            return " ".join(page.extract_text() for page in reader.pages)
        except Exception as e:
            return f"Error reading PDF: {str(e)}"
    
    elif ext in [".txt", ".md"]:
        try:
            return filepath.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    return ""


@app.command()
def index(path: str = typer.Argument(..., help="File or directory path to index")):
    """Index documents into searchable database"""
    init_db()
    
    target = Path(path).resolve()
    if not target.exists():
        console.print(f"[red]Path does not exist: {path}[/red]")
        raise typer.Exit(1)
    
    files = []
    if target.is_file():
        files = [target]
    else:
        for ext in ["*.pdf", "*.txt", "*.md"]:
            files.extend(target.rglob(ext))
    
    if not files:
        console.print("[yellow]No supported files found[/yellow]")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    indexed_count = 0
    
    with console.status("[bold green]Indexing documents..."):
        for file in files:
            content = read_file_content(file)
            if content:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO documents 
                        (filepath, filename, filetype, content, indexed_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        str(file),
                        file.name,
                        file.suffix[1:],
                        content,
                        datetime.now().isoformat()
                    ))
                    indexed_count += 1
                except Exception as e:
                    console.print(f"[red]Error indexing {file.name}: {str(e)}[/red]")
    
    conn.commit()
    conn.close()
    
    console.print(f"[green]Successfully indexed {indexed_count} documents[/green]")


@app.command()
def search(query: str = typer.Argument(..., help="Search query")):
    """Search across indexed documents with keyword highlighting"""
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT filepath, filename, filetype, content
        FROM documents
        WHERE content LIKE ?
    """, (f"%{query}%",))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return
    
    console.print(f"\n[bold]Found {len(results)} results for '{query}':[/bold]\n")
    
    for filepath, filename, filetype, content in results:
        lines = content.split("\n")
        matching_lines = [line for line in lines if query.lower() in line.lower()]
        
        preview = ""
        for line in matching_lines[:3]:
            idx = line.lower().find(query.lower())
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(line), idx + len(query) + 40)
                snippet = line[start:end]
                highlighted = snippet.replace(
                    line[idx:idx+len(query)],
                    f"[bold yellow]{line[idx:idx+len(query)]}[/bold yellow]"
                )
                preview += f"...{highlighted}...\n"
        
        panel = Panel(
            preview.strip() or "No preview available",
            title=f"[cyan]{filename}[/cyan] ({filetype})",
            subtitle=f"[dim]{filepath}[/dim]",
            border_style="blue"
        )
        console.print(panel)


@app.command()
def list():
    """List all indexed files with metadata"""
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT filename, filetype, indexed_at, filepath
        FROM documents
        ORDER BY indexed_at DESC
    """)
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        console.print("[yellow]No indexed documents found[/yellow]")
        return
    
    table = Table(title="Indexed Documents")
    table.add_column("Filename", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Indexed At", style="green")
    table.add_column("Path", style="dim")
    
    for filename, filetype, indexed_at, filepath in results:
        table.add_row(filename, filetype, indexed_at[:19], filepath)
    
    console.print(table)
    console.print(f"\n[bold]Total: {len(results)} documents[/bold]")


@app.command()
def clear():
    """Clear all indexed documents from database"""
    if typer.confirm("Are you sure you want to clear all indexed documents?"):
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents")
        conn.commit()
        conn.close()
        console.print("[green]All documents cleared[/green]")
    else:
        console.print("[yellow]Operation cancelled[/yellow]")


if __name__ == "__main__":
    app()
