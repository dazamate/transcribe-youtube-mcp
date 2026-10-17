"""MCP server that fetches YouTube video transcripts via youtube-transcript-api."""

import os
import re
from urllib.parse import parse_qs, urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)
from youtube_transcript_api.proxies import WebshareProxyConfig

# Keeps a single response under Claude Code's default MCP output limit (~25k tokens).
DEFAULT_MAX_CHARS = 80_000

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

mcp = MCPServer(
    "youtube-transcript",
    instructions=(
        "Fetch transcripts (captions) of YouTube videos. Accepts a video URL or an "
        "11-character video ID. Use list_transcripts to see which languages exist."
    ),
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


def _api() -> YouTubeTranscriptApi:
    # A fresh instance per call: the library's requests.Session isn't thread-safe.
    username = os.environ.get("WEBSHARE_PROXY_USERNAME")
    password = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if username and password:
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(proxy_username=username, proxy_password=password)
        )
    return YouTubeTranscriptApi()


def extract_video_id(video: str) -> str:
    """Return the 11-character video ID from a YouTube URL or bare ID."""
    video = video.strip()
    if VIDEO_ID_RE.match(video):
        return video

    url = urlparse(video if "://" in video else f"https://{video}")
    host = (url.hostname or "").removeprefix("www.").removeprefix("m.").removeprefix("music.")
    candidate = None
    if host == "youtu.be":
        candidate = url.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if url.path == "/watch":
            candidate = parse_qs(url.query).get("v", [None])[0]
        else:
            parts = url.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v", "e"):
                candidate = parts[1]

    if candidate and VIDEO_ID_RE.match(candidate):
        return candidate
    raise ToolError(f"Could not find a YouTube video ID in {video!r}.")


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _language_name(language: str) -> str:
    # The library appends this to generated transcripts' names; we report it separately.
    return language.removesuffix(" (auto-generated)")


def _error(exc: YouTubeTranscriptApiException) -> ToolError:
    if isinstance(exc, CouldNotRetrieveTranscript) and exc.cause:
        return ToolError(f"Could not retrieve transcript for {exc.video_id}: {exc.cause}")
    return ToolError(str(exc).strip())


@mcp.tool(annotations=READ_ONLY)
def get_transcript(
    video: str,
    languages: list[str] | None = None,
    include_timestamps: bool = False,
    offset: int = 0,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Get the transcript of a YouTube video as text.

    Args:
        video: YouTube URL (watch, youtu.be, shorts, embed, live) or 11-character video ID.
        languages: Language codes in priority order, e.g. ["de", "en"]. Defaults to ["en"].
            Manually created transcripts are preferred over auto-generated ones.
        include_timestamps: Prefix each caption line with its [m:ss] start time.
        offset: Character offset to start from, for paging through long transcripts.
        max_chars: Maximum characters to return in this call.
    """
    video_id = extract_video_id(video)
    try:
        fetched = _api().fetch(video_id, languages=languages or ["en"])
    except YouTubeTranscriptApiException as exc:
        raise _error(exc) from exc

    lines = [" ".join(s.text.split()) for s in fetched]
    if include_timestamps:
        text = "\n".join(
            f"[{_format_timestamp(s.start)}] {line}" for s, line in zip(fetched, lines) if line
        )
    else:
        text = " ".join(line for line in lines if line)

    kind = "auto-generated" if fetched.is_generated else "manual"
    header = f"Video: {video_id} | Language: {_language_name(fetched.language)} ({fetched.language_code}, {kind})"

    offset = max(offset, 0)
    chunk = text[offset : offset + max_chars]
    end = offset + len(chunk)
    if offset or end < len(text):
        header += f" | Characters {offset}-{end} of {len(text)}"
    result = f"{header}\n\n{chunk}"
    if end < len(text):
        result += f"\n\n[Truncated. Call again with offset={end} to continue.]"
    return result


@mcp.tool(annotations=READ_ONLY)
def list_transcripts(video: str) -> str:
    """List the transcript languages available for a YouTube video.

    Args:
        video: YouTube URL or 11-character video ID.
    """
    video_id = extract_video_id(video)
    try:
        transcripts = list(_api().list(video_id))
    except YouTubeTranscriptApiException as exc:
        raise _error(exc) from exc

    if not transcripts:
        return f"No transcripts available for {video_id}."
    lines = [f"Transcripts for {video_id}:"]
    for t in transcripts:
        kind = "auto-generated" if t.is_generated else "manual"
        lines.append(f"- {t.language_code}: {_language_name(t.language)} ({kind})")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
