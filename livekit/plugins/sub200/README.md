# Sub200 TTS Plugin (Python)

Lightweight LiveKit Agents plugin that streams speech from Sub200's TTS API.

## Installation

### From PyPI (recommended)

```bash
pip install livekit-plugins-sub200
# or
uv pip install livekit-plugins-sub200
```

### From GitHub (no PyPI)

```bash
pip install git+https://github.com/rangasandbox/livekit-plugins-sub200.git
```

### From workspace checkout

```bash
uv pip install -e livekit-plugins/livekit-plugins-sub200
```

## Quick start

```python
from livekit.plugins import sub200

tts = sub200.TTS(
    model="savara",
    voice="Krishan",
    api_key=os.environ.get("SUB200_API_KEY"),
    base_url=os.environ.get("SUB200_BASE_URL") or "http://tts.sub200.dev/indic-19/v1/tts/generate",
)
```

Plug this `tts` into an `AgentSession`, e.g. see `examples/voice_agents/sub200_agent.py`.

## Configuration

- `SUB200_API_KEY` (required for real requests)
- `SUB200_BASE_URL` (optional override; defaults to the public Indic-19 endpoint)

## Notes

- This plugin uses HTTP chunked streaming and writes optional debug audio/log files when those dirs are provided.
- If no API key is set, requests will fail; the code only logs a warning.
