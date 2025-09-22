# AGENTS instructions

## Overview
This MCP server is primarily a thin wrapper around core saspy features. Enable only the tools you need and disable the rest. A quick start is available in the project README.

## Environment
- Package and project management: uv. For uv-related questions, refer to https://docs.astral.sh/uv/
- Base dependency: saspy. Many issues originate from saspy itself. When troubleshooting, verify saspy works standalone first.

## Dependencies and SDK Notes
- This project is based on FastMCP: https://gofastmcp.com/getting-started/welcome
- The official MCP Python SDK is here: https://github.com/modelcontextprotocol/python-sdk
- Be mindful of:
  - FastMCP vs. official SDK module differences.
  - Version mismatches across docs/samples (FastMCP evolves quickly).
- For complex debugging, consider MCP Inspector. It requires Node.js.
  - If Node.js is available, you can start a dev server like:
    `uv run fastmcp dev server.py`

## Security
- The submit tool can execute arbitrary code. Executing system-level commands (e.g., via SAS X command) can have significant impact.
- Always review code carefully before running it.
- Disable tools you do not need.

## License
- License: FSL-1.1-MIT. Commercial use is NOT permitted until 2027-10.
- If you modify files other than `mcp.json`, ensure your use remains non-commercial and complies with the license.
- If you are unsure about permissions or allowed scope for commercial use, contact: info[at]knworx.com