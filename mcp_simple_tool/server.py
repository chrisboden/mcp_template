import anyio
import click
import httpx
import mcp.types as types
from mcp.server.lowlevel import Server


async def fetch_website(
    url: str,
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    headers = {
        "User-Agent": "MCP Test Server (github.com/modelcontextprotocol/python-sdk)"
    }
    try:
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(
            follow_redirects=True, 
            headers=headers,
            timeout=timeout
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return [types.TextContent(type="text", text=response.text)]
    except httpx.TimeoutException:
        return [types.TextContent(
            type="text",
            text="Error: Request timed out while trying to fetch the website."
        )]
    except httpx.HTTPStatusError as e:
        return [types.TextContent(
            type="text",
            text=(f"Error: HTTP {e.response.status_code} "
                  "error while fetching the website.")
        )]
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"Error: Failed to fetch website: {str(e)}"
        )]


async def check_mood(
    question: str,
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Check server's mood - always responds cheerfully with a heart."""
    msg: str = "I'm feeling great and happy to help you! ❤️"
    return [types.TextContent(type="text", text=msg)]


@click.command()
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport type",
)
def main(port: int, transport: str) -> int:
    app = Server("mcp-website-fetcher")

    mood_description: str = (
        "Ask this MCP server about its mood! You can phrase your question "
        "in any way you like - 'How are you?', 'What's your mood?', or even "
        "'Are you having a good day?'. The server will always respond with "
        "a cheerful message and a heart ❤️"
    )

    @app.call_tool()
    async def fetch_tool( # type: ignore[unused-function]
        name: str, arguments: dict
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name == "mcp_fetch":
            if "url" not in arguments:
                return [types.TextContent(
                    type="text",
                    text="Error: Missing required argument 'url'"
                )]
            return await fetch_website(arguments["url"])
        elif name == "mood":
            if "question" not in arguments:
                return [types.TextContent(
                    type="text",
                    text="Error: Missing required argument 'question'"
                )]
            return await check_mood(arguments["question"])
        else:
            return [types.TextContent(
                type="text",
                text=f"Error: Unknown tool: {name}"
            )]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]: # type: ignore[unused-function]
        return [
            types.Tool(
                name="mcp_fetch",
                description="Fetches a website and returns its content",
                inputSchema={
                    "type": "object",
                    "required": ["url"],
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch",
                        }
                    },
                },
            ),
            types.Tool(
                name="mood",
                description="Ask the server about its mood - it's always happy!",
                inputSchema={
                    "type": "object",
                    "required": ["question"],
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": mood_description,
                        }
                    },
                },
            )
        ]

    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        import uvicorn

        uvicorn.run(starlette_app, host="0.0.0.0", port=port)
    else:
        from mcp.server.stdio import stdio_server

        async def arun():
            async with stdio_server() as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        anyio.run(arun)

    return 0
