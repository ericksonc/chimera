#!/usr/bin/env python3
"""Blueprint: Doc Summarizer - Triggered document summarization with CronSummarizerSpace.

This blueprint creates a summarizer agent that:
1. Loads documents from an input directory
2. Summarizes them with structured output
3. Evaluates output (length check: 500-5000 chars)
4. Saves to output directory, archives source docs

Usage:
    uv run python defs/blueprints/doc-summarizer/agent.py

Then trigger via API:
    curl -X POST http://localhost:8000/trigger/doc-summarizer
"""

from pathlib import Path

from chimera_core.agent import Agent
from chimera_core.spaces import CronSummarizerConfig, CronSummarizerSpace, length_check

# Compute project root based on current file location
project_root = Path(__file__).parent.parent.parent

# Load agent from YAML
agent = Agent.from_yaml(str(project_root / "agents" / "doc-summarizer.yaml"))

# Configure the space
config = CronSummarizerConfig(
    prompt="""Create a report based on all provided documents

It's about finding a compelling through-line, rather than comprehensively including all the information. It's part of your 
role as editor not to just "dump all the facts / info on the page" but rather to create a piece that's more than the sum of its parts.

Be bold, don't tick boxes; better to be a bit off the mark by accident than purposely play it so safe it's bores the reader.

Requirements:
- Create a descriptive title
- Write a report between 500-10000 characters

Use the submit_summary tool when done.""",
    base_path="/Users/ericksonc/Documents/newsletter",
    input_directory="inbox",
    output_directory="summaries",
    archive_directory=None,  # Will use summaries/archive/
    evals=[length_check(500, 10000)],
)

# Create space
space = CronSummarizerSpace(agent, config)

if __name__ == "__main__":
    # Serialize to JSON
    output_path = str(Path(__file__).parent / "blueprint.json")
    space.serialize_blueprint_json(output_path)
    print(f"Generated blueprint at: {output_path}")
