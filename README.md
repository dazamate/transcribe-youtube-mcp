# transcribe-youtube-mcp

An MCP server that gives Claude access to YouTube video transcripts, using
[youtube-transcript-api](https://pypi.org/project/youtube-transcript-api/).

## Tools

- **`get_transcript(video, languages=["en"], include_timestamps=False, offset=0, max_chars=80000)`**
  Returns the transcript as text. `video` can be any YouTube URL (watch, youtu.be,
  shorts, embed, live) or a bare 11-character video ID. Long transcripts are paged:
  the response tells Claude which `offset` to call with next.
- **`list_transcripts(video)`** lists the available languages and whether each
  one is manual or auto-generated.

## Setup

```sh
uv sync
claude mcp add --scope user youtube-transcript -- uv --directory "$PWD" run server.py
```

For Claude Desktop, add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "youtube-transcript": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/transcribe-youtube-mcp", "run", "server.py"]
    }
  }
}
```

## IP blocks

YouTube blocks transcript requests from most cloud-provider IPs and from IPs
that make too many requests. If you hit `IpBlocked`/`RequestBlocked`, set
`WEBSHARE_PROXY_USERNAME` and `WEBSHARE_PROXY_PASSWORD` (Webshare *residential*
proxies) in the server's environment, e.g.
`claude mcp add ... -e WEBSHARE_PROXY_USERNAME=... -e WEBSHARE_PROXY_PASSWORD=...`.
Standard `HTTPS_PROXY` env vars are also respected.
