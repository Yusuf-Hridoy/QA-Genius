"""One engine behind both doors.

Everything in here is a plain function over plain data: no HTTP, no HTML, no
MCP, no AI, no key, no network and nothing stored. The website calls these
from its routes and the MCP server calls them from its tools, so the same
input gives the same answer whichever door it came through.
"""
