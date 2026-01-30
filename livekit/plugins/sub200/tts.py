from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from livekit.agents import (
    APIConnectOptions,
    APIError,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from .log import logger

DEFAULT_BASE_URL = "https://api.sub200.dev/v1/tts/stream"
DEFAULT_MODEL = "orpheus"
DEFAULT_VOICE = "aria"
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_NUM_CHANNELS = 1
DEFAULT_OUTPUT_FORMAT = "wav"


@dataclass
class _RequestConfig:
    url: str
    model: str
    voice: str
    sample_rate: int
    num_channels: int
    api_key: str
    output_format: str
    debug_audio_dir: Path | None
    debug_log_dir: Path | None


class _Sub200ChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        input_text: str,
        conn_options: APIConnectOptions,
        tts_parent: "TTS",
        cfg: _RequestConfig,
    ) -> None:
        super().__init__(tts=tts_parent, input_text=input_text, conn_options=conn_options)
        self._cfg = cfg
        self._file_token = utils.shortuuid()

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        timeout_val = self._conn_options.timeout if self._conn_options.timeout is not None else 120
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=timeout_val, sock_read=timeout_val)

        headers: dict[str, Any] = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Accept": "audio/wav",
            "Content-Type": "application/json",
        }

        payload = {
            "text": self._input_text,
            "model": self._cfg.model,
            "voice": self._cfg.voice,
            "output_format": self._cfg.output_format,
            "stream": True,
        }

        logger.info(
            "sending sub200 TTS request",
            extra={"model": self._cfg.model, "voice": self._cfg.voice, "url": self._cfg.url},
        )

        debug_audio_dir = self._cfg.debug_audio_dir
        debug_log_dir = self._cfg.debug_log_dir

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self._cfg.url, json=payload, headers=headers) as resp:
                    if resp.status in (408, 504):
                        raise APITimeoutError("sub200 TTS request timed out")
                    if resp.status >= 400:
                        raise APIStatusError(resp.status, await resp.text())

                    buffer = bytearray()
                    initialized = False
                    total_bytes = 0
                    request_id = resp.headers.get("x-request-id", utils.shortuuid())

                    wav_path: Path | None = None
                    log_path: Path | None = None
                    file_handle = None

                    if debug_audio_dir:
                        debug_audio_dir.mkdir(parents=True, exist_ok=True)
                    if debug_log_dir:
                        debug_log_dir.mkdir(parents=True, exist_ok=True)

                    async for chunk in resp.content.iter_chunked(4096):
                        if not chunk:
                            continue

                        total_bytes += len(chunk)

                        if not initialized:
                            buffer.extend(chunk)

                            if len(buffer) < 44:
                                # wait for full WAV header before initializing downstream decoder
                                continue

                            if buffer[0:4] != b"RIFF":
                                raise APIError("sub200 returned non-wav payload or empty body")

                            output_emitter.initialize(
                                request_id=request_id,
                                sample_rate=self._cfg.sample_rate,
                                num_channels=self._cfg.num_channels,
                                mime_type="audio/wav",
                            )

                            if debug_audio_dir:
                                wav_path = debug_audio_dir / f"resp_{self._file_token}.wav"
                                file_handle = wav_path.open("wb")
                                file_handle.write(buffer)
                            if debug_log_dir:
                                log_path = debug_log_dir / f"resp_{self._file_token}.txt"

                            initialized = True
                            output_emitter.push(bytes(buffer))
                            buffer.clear()
                            continue

                        output_emitter.push(chunk)
                        if file_handle is not None:
                            file_handle.write(chunk)

                    if not initialized:
                        raise APIError("sub200 returned no audio data")

                    output_emitter.flush()

                    if file_handle is not None:
                        file_handle.flush()
                        file_handle.close()

                    if log_path is not None:
                        log_content = [
                            f"request_id={request_id}",
                            f"text={self._input_text}",
                            f"model={self._cfg.model}",
                            f"voice={self._cfg.voice}",
                            f"url={self._cfg.url}",
                            f"sample_rate={self._cfg.sample_rate}",
                            f"num_channels={self._cfg.num_channels}",
                            f"audio_path={wav_path}",
                            f"total_bytes={total_bytes}",
                        ]
                        log_path.write_text("\n".join(log_content))

                    logger.info(
                        "sub200 stream completed",
                        extra={"request_id": request_id, "total_bytes": total_bytes},
                    )

        except asyncio.TimeoutError as e:
            raise APITimeoutError("sub200 TTS request timed out") from e
        except aiohttp.ClientError as e:
            raise APIError(f"sub200 network error: {e}") from e
        finally:
            try:
                output_emitter.end_input()
            except RuntimeError:
                pass


class TTS(tts.TTS):
    """
    Streaming text-to-speech client for Sub200.

    Parameters:
        model: Model identifier to use (defaults to \"orpheus\").
        voice: Voice to synthesize with (defaults to \"aria\").
        api_key: API key for Sub200. Falls back to SUB200_API_KEY env var or a dummy placeholder.
        base_url: Streaming endpoint. Defaults to Sub200 public TTS stream URL.
        sample_rate: Target audio sample rate. Defaults to 24000 Hz.
        num_channels: Number of audio channels. Defaults to 1 (mono).
        output_format: Expected audio container. Only \"wav\" is validated currently.
        debug_audio_dir: Optional directory to write streamed WAV files.
        debug_log_dir: Optional directory to write request metadata logs.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        voice: str = DEFAULT_VOICE,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        num_channels: int = DEFAULT_NUM_CHANNELS,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        debug_audio_dir: str | Path | None = None,
        debug_log_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=num_channels,
        )

        resolved_api_key = api_key or os.environ.get("SUB200_API_KEY", "")
        if not resolved_api_key:
            logger.warning("SUB200_API_KEY not set; requests will likely fail without it.")

        # Prefer env override, then explicit arg, then library default.
        resolved_base_url = os.environ.get("SUB200_BASE_URL") or base_url or DEFAULT_BASE_URL
        if not resolved_base_url:
            raise ValueError("SUB200_BASE_URL or base_url must be provided for Sub200 TTS")

        self._cfg = _RequestConfig(
            url=resolved_base_url,
            model=model,
            voice=voice,
            sample_rate=sample_rate,
            num_channels=num_channels,
            api_key=resolved_api_key,
            output_format=output_format,
            debug_audio_dir=Path(debug_audio_dir) if debug_audio_dir else None,
            debug_log_dir=Path(debug_log_dir) if debug_log_dir else None,
        )

    @property
    def model(self) -> str:
        return self._cfg.model

    @property
    def voice(self) -> str:
        return self._cfg.voice

    @property
    def provider(self) -> str:
        return "sub200"

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        return _Sub200ChunkedStream(
            input_text=text,
            conn_options=conn_options,
            tts_parent=self,
            cfg=self._cfg,
        )
