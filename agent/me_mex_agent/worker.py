"""Long-lived LiveKit worker — bridges room audio/data to Colab STT/TTS and backend graph."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

try:
    from livekit import rtc
    from livekit.agents import JobContext, WorkerOptions, cli
except ImportError:  # pragma: no cover
    rtc = None
    JobContext = Any  # type: ignore[misc,assignment]
    WorkerOptions = Any
    cli = None

from me_mex_agent.audio_util import (
    float32_to_pcm16,
    pcm16_mono_to_wav,
    should_end_utterance,
)
from me_mex_agent.speech_colab import speech_enabled, synthesize_wav, transcribe_wav
from me_mex_agent.turn_bridge import post_resume, run_turn_with_reply

_log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SILENCE_RMS = float(os.getenv("VOICE_SILENCE_RMS", "0.008"))
MIN_UTTERANCE_MS = int(os.getenv("VOICE_MIN_UTTERANCE_MS", "400"))
MAX_UTTERANCE_MS = int(os.getenv("VOICE_MAX_UTTERANCE_MS", "20000"))
END_SILENCE_MS = int(os.getenv("VOICE_END_SILENCE_MS", "1500"))


@dataclass
class RoomSession:
    thread_id: str = "livekit"
    context_json: dict[str, Any] = field(default_factory=dict)
    muted: bool = True
    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    cancel_tts: asyncio.Event = field(default_factory=asyncio.Event)
    tts_source: Any = None
    tts_track: Any = None


def _parse_data(payload: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


async def _ensure_tts_track(room: rtc.Room, session: RoomSession) -> None:
    if session.tts_source is not None:
        return
    source = rtc.AudioSource(24000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent_voice", source)
    await room.local_participant.publish_track(track)
    session.tts_source = source
    session.tts_track = track


async def _play_wav(room: rtc.Room, session: RoomSession, wav: bytes) -> None:
    if not wav:
        return
    import io
    import wave

    session.cancel_tts.clear()
    await _ensure_tts_track(room, session)
    assert session.tts_source is not None
    with wave.open(io.BytesIO(wav), "rb") as wf:
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if rate != 24000:
        _log.warning("TTS wav sample rate %s (expected 24000)", rate)
    samples_per_channel = len(frames) // 2
    import struct

    offset = 0
    frame_samples = 480  # 20ms @ 24kHz
    while offset < samples_per_channel:
        if session.cancel_tts.is_set():
            return
        chunk = frames[offset * 2 : (offset + frame_samples) * 2]
        offset += frame_samples
        if len(chunk) < 2:
            break
        count = len(chunk) // 2
        pcm = struct.unpack(f"<{count}h", chunk)
        floats = [x / 32768.0 for x in pcm]
        frame = rtc.AudioFrame(
            data=float32_to_pcm16(floats),
            sample_rate=24000,
            num_channels=1,
            samples_per_channel=count,
        )
        await session.tts_source.capture_frame(frame)


async def _forward_dock_events(room: rtc.Room, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    payload = json.dumps({"type": "dock_events", "events": events}).encode("utf-8")
    await room.local_participant.publish_data(payload, reliable=True)


async def _run_voice_turn(room: rtc.Room, session: RoomSession, text: str) -> None:
    if session.muted or not text.strip():
        return
    context = dict(session.context_json)
    context.setdefault("muted", session.muted)
    project_id = context.get("active_project_id") or context.get("project_id")
    if not project_id:
        _log.warning("No active_project_id in context_json; skipping turn")
        return
    session.cancel_tts.set()
    async with session.turn_lock:
        try:
            reply, events, turn_end = await run_turn_with_reply(
                text=text,
                thread_id=session.thread_id,
                context_json=context,
            )
        except httpx.HTTPError:
            _log.exception("voice_turn failed")
            return
        await _forward_dock_events(room, events)
        if turn_end.get("details", {}).get("approval_id") or any(
            e.get("type") == "approval" for e in events
        ):
            await room.local_participant.publish_data(
                json.dumps({"type": "awaiting_approval", "turn": turn_end}).encode(),
                reliable=True,
            )
        if reply.strip():
            _log.info("voice_turn reply_len=%d", len(reply.strip()))
        if reply.strip() and speech_enabled():
            try:
                wav = await synthesize_wav(reply)
                await _play_wav(room, session, wav)
            except httpx.HTTPError:
                _log.exception("TTS failed")
        elif reply.strip():
            await room.local_participant.publish_data(
                json.dumps({"type": "agent_reply", "text": reply}).encode(),
                reliable=True,
            )


def _schedule_voice_turn(room: rtc.Room, session: RoomSession, text: str) -> None:
    if session.turn_lock.locked():
        _log.warning(
            "turn in progress, utterance dropped: %r",
            text.strip()[:120],
        )
        return

    async def _guarded() -> None:
        try:
            await _run_voice_turn(room, session, text)
        except Exception:  # noqa: BLE001
            _log.exception("voice_turn failed")

    asyncio.create_task(_guarded())


async def _handle_data(payload: bytes, room: rtc.Room, session: RoomSession) -> None:
    msg = _parse_data(payload)
    if not msg:
        return
    mtype = msg.get("type")
    if mtype == "context_update":
        session.context_json.update(msg.get("context_json") or {})
        if msg.get("thread_id"):
            session.thread_id = msg["thread_id"]
        session.muted = bool(msg.get("muted", session.muted))
        _log.info(
            "context_update muted=%s project=%s thread=%s",
            session.muted,
            session.context_json.get("active_project_id"),
            session.thread_id,
        )
        return
    if mtype in ("approve", "cancel"):
        action = "approve" if mtype == "approve" else "dismiss"
        await post_resume(
            thread_id=session.thread_id,
            approval_id=msg.get("approval_id", ""),
            action=action,
            context_json=session.context_json,
        )
        return
    if mtype == "agent_turn":
        _schedule_voice_turn(room, session, msg.get("text", ""))
        return
    if mtype == "speech_wav":
        raw = base64.b64decode(msg.get("data") or "")
        if raw:
            try:
                result = await transcribe_wav(raw)
                text = (result.get("text") or "").strip()
                if text:
                    _schedule_voice_turn(room, session, text)
            except httpx.HTTPError:
                _log.exception("STT failed")


async def _consume_audio_track(
    track: rtc.Track,
    room: rtc.Room,
    session: RoomSession,
) -> None:
    stream = rtc.AudioStream(track)
    buffer: list[float] = []
    sample_rate = 48000
    silent_ms = 0
    speaking_ms = 0
    async for event in stream:
        if session.muted:
            buffer.clear()
            silent_ms = 0
            speaking_ms = 0
            continue
        frame = event.frame
        sample_rate = frame.sample_rate
        import struct

        samples = struct.unpack(
            f"<{frame.samples_per_channel}h", frame.data[: frame.samples_per_channel * 2]
        )
        floats = [s / 32768.0 for s in samples]
        rms = _rms(floats)
        frame_ms = int(1000 * len(floats) / sample_rate)
        if rms > SILENCE_RMS:
            buffer.extend(floats)
            speaking_ms += frame_ms
            silent_ms = 0
        else:
            if buffer:
                silent_ms += frame_ms
        if should_end_utterance(
            speaking_ms=speaking_ms,
            silent_ms=silent_ms,
            buffer_nonempty=bool(buffer),
            min_utterance_ms=MIN_UTTERANCE_MS,
            max_utterance_ms=MAX_UTTERANCE_MS,
            end_silence_ms=END_SILENCE_MS,
        ):
            duration_s = len(buffer) / float(sample_rate) if sample_rate else 0.0
            pcm = float32_to_pcm16(buffer)
            wav = pcm16_mono_to_wav(pcm, sample_rate=sample_rate)
            buffer.clear()
            silent_ms = 0
            speaking_ms = 0
            if not speech_enabled():
                continue
            try:
                result = await transcribe_wav(wav)
                text = (result.get("text") or "").strip()
                _log.info(
                    "STT utterance (%.2fs, %d bytes wav): %r",
                    duration_s,
                    len(wav),
                    text[:120],
                )
                if text:
                    _schedule_voice_turn(room, session, text)
            except httpx.HTTPError:
                _log.exception("STT failed")


def _start_audio_consumer(
    track: rtc.Track,
    room: rtc.Room,
    session: RoomSession,
    participant: rtc.RemoteParticipant,
) -> None:
    _log.info("consuming audio track from %s", participant.identity)
    # context_update can race agent join; a published user mic means an active voice session.
    session.muted = False
    asyncio.create_task(_consume_audio_track(track, room, session))


def _attach_existing_audio(room: rtc.Room, session: RoomSession) -> None:
    for participant in room.remote_participants.values():
        for pub in participant.track_publications.values():
            if pub.track and pub.kind == rtc.TrackKind.KIND_AUDIO:
                _start_audio_consumer(pub.track, room, session, participant)


async def entrypoint(ctx: JobContext) -> None:
    if rtc is None:
        raise RuntimeError("livekit-agents not installed")
    room = ctx.room
    session = RoomSession()

    @room.on("data_received")
    def _on_data(packet: rtc.DataPacket) -> None:
        asyncio.create_task(_handle_data(packet.data, room, session))

    @room.on("track_subscribed")
    def _on_track(
        track: rtc.Track,
        _pub: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if participant.identity == room.local_participant.identity:
            return
        _start_audio_consumer(track, room, session, participant)

    await ctx.connect()
    _log.info("agent joined room %s", room.name)
    _attach_existing_audio(room, session)


def main() -> None:
    if cli is None:
        raise RuntimeError("Install livekit-agents to run the worker")
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
