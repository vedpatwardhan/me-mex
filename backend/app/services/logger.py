import os
import sys
import time
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# Custom styling theme for Me-Mex backend workflows
_THEME = Theme(
    {
        "ingestion": "bold cyan",
        "retrieval": "bold green",
        "conversation": "bold magenta",
        "database": "bold blue",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "dim white",
        "highlight": "bold yellow",
        "node": "cyan",
        "success": "bold green",
    }
)


def _get_active_terminal_stream():
    """Acquires direct terminal file descriptor /dev/tty to bypass pytest/xdist pipes, falling back to sys.stderr."""
    try:
        if os.path.exists("/dev/tty"):
            return open("/dev/tty", "w", buffering=1, encoding="utf-8")
    except Exception as e:
        # Fall back to standard error when /dev/tty is unavailable (e.g. non-interactive environments)
        sys.stderr.write(
            f"[RichLogger WARNING] /dev/tty unavailable ({e}), using sys.stderr\n"
        )
    return sys.stderr


# Standard console for output, forced to terminal mode for guaranteed color and instant flushing
console = Console(file=_get_active_terminal_stream(), theme=_THEME, force_terminal=True)


class RichLogger:
    """Centralized structured logger for Me-Mex workflows."""

    @staticmethod
    def phase_header(
        title: str, subtitle: Optional[str] = None, style: str = "cyan"
    ) -> None:
        """Prints a bordered panel with vertical margin to clearly separate major pipeline phases."""
        content = Text(title, style=f"bold {style}")
        if subtitle:
            content.append(f"\n{subtitle}", style="dim white")
        console.print()
        console.print(Panel(content, border_style=style, expand=False, padding=(0, 2)))
        console.print()

    @staticmethod
    def tree_branch(message: str, prefix: str = "  ├─ ", style: str = "white") -> None:
        """Prints an indented tree branch item with custom styling."""
        console.print(f"{prefix}[{style}]{message}[/{style}]")

    @staticmethod
    def tree_subitem(
        message: str, indent: str = "  │   • ", style: str = "dim white"
    ) -> None:
        """Prints a nested bullet item within a tree branch."""
        console.print(f"{indent}[{style}]{message}[/{style}]")

    @staticmethod
    def tree_leaf(
        message: str, prefix: str = "  ╰─ ", style: str = "bold green"
    ) -> None:
        """Prints the terminal closing leaf of a tree phase with vertical margin."""
        console.print(f"{prefix}[{style}]{message}[/{style}]")
        console.print()

    @staticmethod
    def error_box(title: str, error_details: str) -> None:
        """Renders an explicit, attention-grabbing error panel."""
        console.print()
        err_text = Text(f"{title}\n", style="bold red")
        err_text.append(error_details, style="white")
        console.print(
            Panel(err_text, border_style="bold red", expand=False, padding=(0, 2))
        )
        console.print()

    @staticmethod
    def warning(message: str) -> None:
        """Prints a styled warning message."""
        console.print(
            f"  [bold yellow]⚠️  WARNING:[/bold yellow] [yellow]{message}[/yellow]"
        )

    @staticmethod
    def info(message: str, style: str = "dim white") -> None:
        """Prints a styled info message."""
        console.print(f"  [{style}]{message}[/{style}]")

    @staticmethod
    def log_event(project_id: str, event_type: str, event_data: Dict[str, Any]) -> None:
        """Formats and prints an event from EphemeralEventQueue with rich styling and full telemetry."""
        # Suppress raw token chunks from console spam
        if event_type == "token_chunk":
            return

        proj_badge = f"[dim][{project_id}][/dim]"

        # --- Phase 1: Intent Classification ---
        if event_type == "intent_classified":
            intent = event_data.get("intent", "UNKNOWN")
            duration = event_data.get("duration_seconds")
            duration_str = f" [dim]({duration}s)[/dim]" if duration is not None else ""
            style = (
                "cyan"
                if intent == "INGESTION"
                else ("green" if intent == "RETRIEVAL" else "magenta")
            )
            doc_type_str = (
                f" • doc_type: [bold]{event_data.get('doc_type')}[/bold]"
                if event_data.get("doc_type")
                else ""
            )
            url_str = (
                f" • url: [dim]{event_data.get('source_url')}[/dim]"
                if event_data.get("source_url")
                else ""
            )
            console.print()
            console.print(
                f"{proj_badge} [bold {style}]⚡ INTENT EVALUATED: {intent}[/bold {style}]{duration_str}{doc_type_str}{url_str}"
            )

        # --- Phase 2: Ingestion Pipeline Events ---
        elif event_type == "document_fetched":
            url = event_data.get("url") or event_data.get("source_url", "")
            doc_type = event_data.get("doc_type", "document")
            chars = event_data.get("char_count")
            pages = event_data.get("page_count")
            debug_path = event_data.get("debug_file_path", "")
            filename = os.path.basename(debug_path) if debug_path else ""

            meta_parts = []
            if doc_type:
                meta_parts.append(f"type: {doc_type}")
            if pages:
                meta_parts.append(f"{pages} pages")
            if chars:
                meta_parts.append(f"{chars:,} chars")
            meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""

            console.print(
                f"{proj_badge}   ├─ 📄 [bold cyan]Document Fetched[/bold cyan]: [underline]{url}[/underline]{meta_str}"
            )
            if filename:
                console.print(
                    f"      │   • cached to: [dim]temp_downloads/{filename}[/dim]"
                )

        elif event_type == "orchestrator_tool_call":
            tool = event_data.get("tool_name") or event_data.get("tool", "")
            title = event_data.get("doc_title") or event_data.get("args", {}).get(
                "title", ""
            )
            console.print(
                f"{proj_badge}   ├─ 🛠️  [bold blue]Tool Invocation[/bold blue]: [cyan]{tool}[/cyan] for '{title}'"
            )

        elif event_type == "passages_chunked":
            count = event_data.get("chunk_count", 0)
            title = event_data.get("doc_title", "Document")
            console.print(
                f"{proj_badge}   ├─ ✂️  [bold yellow]Passages Chunked[/bold yellow]: [bold]{count} adaptive passages[/bold] generated for '{title}'"
            )

        elif event_type == "passage_extraction_progress":
            idx = event_data.get("chunk_index", 0)
            total = event_data.get("total_chunks", 0)
            c_count = event_data.get("concepts_extracted", 0)
            c_titles = event_data.get("concept_titles", [])
            duration = event_data.get("duration_seconds")
            duration_str = f" [dim]({duration}s)[/dim]" if duration is not None else ""
            titles_str = ""
            if c_titles:
                titles_formatted = ", ".join(
                    f"[bold cyan]'{t}'[/bold cyan]" for t in c_titles
                )
                titles_str = f": {titles_formatted}"
            console.print(
                f"{proj_badge}   │   • [dim]Chunk [{idx}/{total}][/dim]: extracted [bold green]+{c_count} concepts[/bold green]{duration_str}{titles_str}"
            )

        elif event_type == "passages_extracted":
            c_count = event_data.get("raw_concept_count", 0)
            title = event_data.get("doc_title", "")
            console.print(
                f"{proj_badge}   ├─ 📦 [bold green]Passage Extraction Complete[/bold green]: [bold]{c_count} raw concepts[/bold] from '{title}'"
            )

        elif event_type == "consolidation_start":
            c_count = event_data.get("raw_concept_count", 0)
            title = event_data.get("doc_title", "")
            console.print(
                f"{proj_badge}   ├─ 🧠 [bold magenta]Concept Consolidation Starting[/bold magenta]: deduplicating [bold]{c_count} raw concepts[/bold] into canonical graph nodes..."
            )

        elif event_type == "consolidation_complete":
            c_count = event_data.get("canonical_concepts_count", 0)
            title = event_data.get("doc_title", "")
            canonical_concepts = event_data.get("canonical_concepts", [])
            duration = event_data.get("duration_seconds")
            duration_str = f" [dim]({duration}s)[/dim]" if duration is not None else ""
            console.print(
                f"{proj_badge}   ├─ 🎯 [bold magenta]Consolidation Complete[/bold magenta]: synthesized [bold]{c_count} canonical concepts[/bold]{duration_str}"
            )
            if canonical_concepts:
                concepts_str = ", ".join(
                    f"[bold cyan]'{c}'[/bold cyan]" for c in canonical_concepts
                )
                console.print(
                    f"{proj_badge}   │   • [magenta]Canonical Concepts Synthesized:[/magenta] {concepts_str}"
                )

        elif event_type == "root_node_created":
            title = event_data.get("title", "")
            node_type = event_data.get("node_type", "ROOT")
            node_id = event_data.get("root_node_id", "")
            console.print(
                f"{proj_badge}   ├─ 🏛️  [bold cyan]Root Node Created[/bold cyan]: [bold]{title}[/bold] (type: [yellow]{node_type}[/yellow], id: [dim]{node_id}[/dim], [green]immutable: true[/green])"
            )

        elif event_type == "intra_concepts_created":
            count = event_data.get("count", 0)
            root_id = event_data.get("root_node_id", "")
            console.print(
                f"{proj_badge}   ├─ 🔗 [bold cyan]Intra-Document Concepts Created[/bold cyan]: [bold]{count} concepts[/bold] linked to [dim]{root_id}[/dim]"
            )

        elif event_type == "hubs_calculated":
            count = event_data.get("count", 0)
            hubs = event_data.get("hubs", [])
            hub_str = ", ".join(f"'{h.get('title')}' ({h.get('score')})" for h in hubs)
            console.print(
                f"{proj_badge}   ├─ 🌐 [bold blue]Top Concept Hubs Computed[/bold blue]: {count} hubs ({hub_str})"
            )

        elif event_type == "persona_routing_completed":
            msg = event_data.get("message", "Persona routing completed.")
            console.print(f"{proj_badge}   ├─ 🎯 [bold green]{msg}[/bold green]")

        elif event_type == "partitions_calculated":
            partitions = event_data.get("partitions", {})
            parts_summary = ", ".join(
                f"{dept} ({len(nodes)} nodes)"
                for dept, nodes in list(partitions.items())
            )
            console.print(
                f"{proj_badge}   ├─ 🧩 [bold blue]Mutually Exclusive Partitions[/bold blue]: {len(partitions)} communities ({parts_summary})"
            )

        elif event_type == "persona_traversal_start":
            msg = (
                event_data.get("message")
                or f"Persona for '{event_data.get('department_name', '')}' exploring sub-graph..."
            )
            console.print(f"{proj_badge}   ├─ 🧭 [dim]{msg}[/dim]")

        elif event_type == "persona_traversal_active":
            dept = event_data.get("department_name", "Specialist Persona")
            traversed = event_data.get("traversed_node_ids", [])
            console.print(
                f"{proj_badge}   │   • [dim]Persona [{dept}][/dim]: traversed [bold]{len(traversed)} adjacent nodes[/bold]"
            )

        elif event_type == "node_touched":
            node = event_data.get("node_title") or event_data.get("node", "")
            detail = event_data.get("message", "")
            detail_str = f" - {detail}" if detail else ""
            console.print(
                f"{proj_badge}   │   • [cyan]Node Touched[/cyan]: '{node}'{detail_str}"
            )

        elif event_type == "ingestion_completed":
            msg = event_data.get(
                "message",
                "Document successfully ingested and merged into knowledge graph.",
            )
            console.print(
                f"{proj_badge}   ╰─ [bold green]✅ INGESTION COMPLETED[/bold green]: {msg}"
            )
            console.print()

        # --- Phase 3: Retrieval & Conversation Events ---
        elif event_type == "conversation_start":
            console.print(
                f"{proj_badge}   ├─ 💬 [bold magenta]Streaming Conversational Response[/bold magenta]..."
            )

        elif event_type == "retrieval_summary":
            msg = event_data.get("message", "Graph retrieval completed.")
            console.print(
                f"{proj_badge}   ├─ 📊 [bold green]Retrieval Synthesis[/bold green]: {msg}"
            )

        elif event_type == "chat_complete":
            console.print(
                f"{proj_badge}   ╰─ [bold green]✓ Turn Complete[/bold green]: response streamed & chat history persisted."
            )
            console.print()

        # --- Errors & Failures ---
        elif event_type in ("error", "extraction_failed", "consolidation_failed"):
            err = event_data.get("error") or event_data.get(
                "message", "An unknown error occurred."
            )
            console.print(
                f"{proj_badge}   ❌ [bold red]{event_type.upper()}[/bold red]: {err}"
            )
            console.print()

        # --- Generic Fallback ---
        else:
            msg = event_data.get("message", "")
            msg_str = f" - {msg}" if msg else ""
            console.print(f"{proj_badge} 📡 [dim]{event_type}[/dim]{msg_str}")


logger = RichLogger()
