import json
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from app.db import db_engine
from app.models import GraphNode, GraphEdge, PassageRecord
from app.tools.search_tools import search_tools
from app.services.graph_analytics import graph_analytics

# Initialize FastMCP Server
mcp = FastMCP("Graph-Memex Agent Tools")


@mcp.tool()
def search_duckduckgo_web(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo web search engine for live web pages, snippets, and URLs."""
    results = search_tools.search_duckduckgo(query, max_results=max_results)
    return json.dumps(results, indent=2)


@mcp.tool()
def search_arxiv_papers(query: str, max_results: int = 3) -> str:
    """Search ArXiv API for papers relevant to a research topic."""
    results = search_tools.search_arxiv(query, max_results=max_results)
    return json.dumps(results, indent=2)


@mcp.tool()
def fetch_web_article(url: str) -> str:
    """Fetch and extract clean plain-text markdown content from web page or blog URL."""
    res = search_tools.fetch_document(url)
    return json.dumps(res, indent=2)


@mcp.tool()
def get_graph_nodes(project_id: str = "global") -> str:
    """Retrieve all atomic graph concept nodes from the database."""
    nodes = db_engine.get_nodes(project_id)
    return json.dumps([n.model_dump(by_alias=True) for n in nodes], indent=2)


@mcp.tool()
def get_passages_by_ids(passage_ids: List[str]) -> str:
    """Retrieve out-of-graph plain text passage records linked to concept nodes."""
    passages = db_engine.get_passages(passage_ids)
    return json.dumps([p.model_dump(by_alias=True) for p in passages], indent=2)


@mcp.tool()
def get_macro_documents() -> str:
    """Retrieve Department Macro Documents with top hub concept IDs and summaries."""
    macros = db_engine.get_macros()
    return json.dumps([m.model_dump(by_alias=True) for m in macros], indent=2)


@mcp.tool()
def calculate_hub_rankings() -> str:
    """Calculate degree and eigenvector hub centrality for graph nodes."""
    centrality = graph_analytics.calculate_hub_centrality()
    return json.dumps(centrality, indent=2)


if __name__ == "__main__":
    print("[FastMCP] Starting Graph-Memex FastMCP Server...")
    mcp.run()
