# Sub200 plugin for LiveKit Agents

This plugin adds Sub200 text-to-speech (TTS) support to the LiveKit Agent Framework.
It wraps Sub200's streaming endpoint so you can drop it into any voice pipeline.

## Installation

From the repo root (workspace aware):

```bash
uv pip install -e livekit-plugins/livekit-plugins-sub200
```

## Usage

```python
from livekit.plugins import sub200

tts = sub200.TTS(
    model="orpheus",
    voice="aria",
)

agent = VoicePipelineAgent(
    tts=tts,
    # stt=..., llm=..., vad=..., etc.
)
```

See `examples/voice_agents/sub200_agent.py` for a full AgentSession integration.

## Configuration

- `SUB200_API_KEY` (env var): authentication for the Sub200 API. Leave unset only if you're running
  offline; requests will fail without a valid key.
- Optional parameters on `TTS`:
  - `model` (default `"orpheus"`)
  - `voice` (default `"aria"`)
  - `base_url` (stream endpoint, defaults to Sub200 public API)
  - `sample_rate`, `num_channels`
  - `debug_audio_dir`, `debug_log_dir` for saving streamed audio/logs locally
