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
    from livekit.agents import JobContext, JobProcess, WorkerOptions, cli
except ImportError:  # pragma: no cover
    rtc = None
    JobContext = Any  # type: ignore[misc,assignment]
    JobProcess = Any  # type: ignore[misc,assignment]
    WorkerOptions = Any
    cli = None

from voice_agent.audio_util import (
    float32_to_pcm16,
    frame_to_mono_floats,
    pcm16_mono_to_wav,
    should_end_utterance,
)
from voice_agent.speech_colab import speech_enabled, synthesize_wav, transcribe_wav
from voice_agent.tts_pipeline import TtsPipeline, pipelined_tts_enabled
from voice_agent.turn_bridge import post_resume, run_turn_with_reply, stream_session_events
from voice_agent.vad_silero import (
    SileroUtteranceCollector,
    load_silero_vad,
    voice_vad_mode,
)

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
    cancel_turn: asyncio.Event = field(default_factory=asyncio.Event)
    tts_source: Any = None
    tts_track: Any = None
    audio_consumer_started: bool = False
    peak_rms: float = 0.0
    utterance_collector: SileroUtteranceCollector | None = None
    stt_semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    vad: Any = None
    proactive_spoken: set[str] = field(default_factory=set)
    session_events_task: asyncio.Task | None = None


def _parse_data(payload: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def prewarm(proc: JobProcess) -> None:
    if voice_vad_mode() != "silero":
        _log.info("VOICE_VAD=rms — Silero not loaded in prewarm")
        return
    proc.userdata["vad"] = load_silero_vad()


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
    _log.info("TTS playback start (%d bytes wav)", len(wav))
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
    _log.info("TTS playback done")


async def _publish_dock_event(room: rtc.Room, chunk: dict[str, Any]) -> None:
    await room.local_participant.publish_data(
        json.dumps({"type": "dock_event", "event": chunk}).encode("utf-8"),
        reliable=True,
    )


async def _forward_dock_events(room: rtc.Room, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    payload = json.dumps({"type": "dock_events", "events": events}).encode("utf-8")
    await room.local_participant.publish_data(payload, reliable=True)


def _should_run_turn(session: RoomSession, text: str) -> bool:
    fields = (session.context_json or {}).get("custom_fields") or {}
    if fields.get("intent") or fields.get("resume_job_id") or fields.get("force_project_scope"):
        return True
    return bool(text.strip())


async def _run_voice_turn(room: rtc.Room, session: RoomSession, text: str) -> None:
    if session.muted and not _should_run_turn(session, text):
        return
    if not _should_run_turn(session, text):
        return
    context = dict(session.context_json)
    context.setdefault("muted", session.muted)
    context["voice_turn"] = True
    project_id = context.get("active_project_id") or context.get("project_id")
    if not project_id:
        _log.warning("No active_project_id in context_json; skipping turn")
        return
    session.cancel_tts.set()
    session.cancel_turn.clear()
    await room.local_participant.publish_data(
        json.dumps({"type": "turn_start", "text": text.strip()[:500]}).encode(),
        reliable=True,
    )
    _ensure_session_events_listener(room, session)
    async with session.turn_lock:
        use_pipeline = speech_enabled() and pipelined_tts_enabled()
        tts_pipeline: TtsPipeline | None = None
        if use_pipeline:
            session.cancel_tts.clear()
            tts_pipeline = TtsPipeline(
                synthesize=synthesize_wav,
                play_wav=_play_wav,
                cancel_event=session.cancel_tts,
                session=session,
                room=room,
            )
            await tts_pipeline.start()

        async def on_chunk(chunk: dict[str, Any]) -> None:
            if session.cancel_turn.is_set():
                return
            await _publish_dock_event(room, chunk)
            if tts_pipeline and chunk.get("type") == "token":
                src = chunk.get("source")
                if src in (None, "conversation"):
                    tts_pipeline.feed_token(chunk.get("content") or "")

        try:
            reply, events, turn_end = await run_turn_with_reply(
                text=text,
                thread_id=session.thread_id,
                context_json=context,
                on_chunk=on_chunk,
            )
        except httpx.HTTPError:
            _log.exception("voice_turn failed thread_id=%s", session.thread_id)
            if tts_pipeline:
                await tts_pipeline.cancel()
            return
        if turn_end:
            await _publish_dock_event(room, turn_end)
        await _forward_dock_events(room, events)
        if turn_end.get("details", {}).get("approval_id") or any(
            e.get("type") == "approval" for e in events
        ):
            await room.local_participant.publish_data(
                json.dumps({"type": "awaiting_approval", "turn": turn_end}).encode(),
                reliable=True,
            )
        if reply.strip():
            _log.info(
                "voice_turn thread_id=%s reply_len=%d",
                session.thread_id,
                len(reply.strip()),
            )
        if reply.strip() and speech_enabled():
            try:
                if tts_pipeline:
                    await tts_pipeline.finish()
                else:
                    wav = await synthesize_wav(reply)
                    await _play_wav(room, session, wav)
            except httpx.HTTPError:
                _log.exception("TTS failed")
        elif reply.strip():
            await room.local_participant.publish_data(
                json.dumps({"type": "agent_reply", "text": reply}).encode(),
                reliable=True,
            )


async def _maybe_proactive_tts(
    room: rtc.Room,
    session: RoomSession,
    *,
    job_id: str,
    text: str,
) -> None:
    if not text.strip() or session.muted or not speech_enabled():
        return
    stripped = text.strip()
    if stripped.startswith("Finished ") and len(stripped) < 120:
        return
    if job_id in session.proactive_spoken:
        return
    session.proactive_spoken.add(job_id)
    session.cancel_tts.set()
    try:
        wav = await synthesize_wav(text.strip())
        await _play_wav(room, session, wav)
    except httpx.HTTPError:
        _log.exception("proactive TTS failed")


async def _consume_session_events(room: rtc.Room, session: RoomSession) -> None:
    project_id = session.context_json.get("active_project_id") or session.context_json.get(
        "project_id"
    )
    if not project_id:
        return
    try:
        async for ev in stream_session_events(
            project_id=str(project_id),
            thread_id=session.thread_id,
        ):
            if ev.get("type") == "proactive":
                jid = str(ev.get("job_id") or "")
                line = str(ev.get("text") or "")
                await _maybe_proactive_tts(room, session, job_id=jid or line[:32], text=line)
                await room.local_participant.publish_data(
                    json.dumps({"type": "proactive_reply", "text": line, "job_id": jid}).encode(),
                    reliable=True,
                )
            elif ev.get("type") in ("job_update", "recommendation"):
                await room.local_participant.publish_data(
                    json.dumps({"type": ev["type"], **ev}).encode(),
                    reliable=True,
                )
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        _log.exception("session events stream ended")


def _ensure_session_events_listener(room: rtc.Room, session: RoomSession) -> None:
    project_id = session.context_json.get("active_project_id") or session.context_json.get(
        "project_id"
    )
    if not project_id:
        return
    task = session.session_events_task
    if task is not None and not task.done():
        return
    session.session_events_task = asyncio.create_task(_consume_session_events(room, session))


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


def _schedule_stt_pipeline(
    room: rtc.Room,
    session: RoomSession,
    wav: bytes,
    duration_s: float,
    reason: str,
) -> None:
    async def _run() -> None:
        async with session.stt_semaphore:
            if not speech_enabled():
                _log.warning(
                    "VAD utterance (%.2fs, %s) ready but COLAB_INFERENCE_BASE_URL unset",
                    duration_s,
                    reason,
                )
                return
            _log.info(
                "VAD utterance ready (%.2fs, %d bytes wav, flush=%s) → Colab STT",
                duration_s,
                len(wav),
                reason,
            )
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

    asyncio.create_task(_run())


async def _handle_data(payload: bytes, room: rtc.Room, session: RoomSession) -> None:
    msg = _parse_data(payload)
    if not msg:
        return
    mtype = msg.get("type")
    if mtype == "context_update":
        session.context_json.update(msg.get("context_json") or {})
        if msg.get("thread_id"):
            session.thread_id = msg["thread_id"]
        was_muted = session.muted
        new_muted = bool(msg.get("muted", session.muted))
        if was_muted != new_muted and new_muted and session.utterance_collector is not None:
            await session.utterance_collector.flush_mute()
        session.muted = new_muted
        # Barge-in only when the user actually un-mutes, not on duplicate context_update.
        if not session.muted and was_muted:
            session.cancel_tts.set()
            session.cancel_turn.set()
            session.peak_rms = 0.0
        elif not was_muted and session.muted and session.peak_rms > 0:
            _log.info(
                "mic muted (peak_rms=%.4f)",
                session.peak_rms,
            )
        _ensure_session_events_listener(room, session)
        _log.info(
            "context_update muted=%s project=%s thread=%s",
            session.muted,
            session.context_json.get("active_project_id"),
            session.thread_id,
        )
        return
    if mtype in ("approve", "cancel"):
        action = "approve" if mtype == "approve" else "dismiss"
        session.cancel_tts.set()
        try:
            result = await post_resume(
                thread_id=session.thread_id,
                approval_id=msg.get("approval_id", ""),
                action=action,
                context_json=session.context_json,
            )
        except httpx.HTTPError:
            _log.exception("resume failed")
            return
        reply = str(result.get("reply") or result.get("status") or "Done.")
        await _publish_dock_event(
            room,
            {"type": "turn_end", "reply": reply, "graph_write": True, "details": result},
        )
        if reply.strip() and speech_enabled():
            try:
                await _play_wav(room, session, await synthesize_wav(reply[:2000]))
            except httpx.HTTPError:
                _log.exception("TTS failed after resume")
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


async def _consume_audio_track_rms(
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
        floats, frame_ms = frame_to_mono_floats(frame)
        if not floats:
            continue
        rms = _rms(floats)
        session.peak_rms = max(session.peak_rms, rms)
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
            _schedule_stt_pipeline(room, session, wav, duration_s, "rms")


async def _consume_audio_track_silero(
    track: rtc.Track,
    room: rtc.Room,
    session: RoomSession,
    vad: Any,
) -> None:
    async def on_utterance(wav: bytes, duration_s: float, reason: str) -> None:
        _schedule_stt_pipeline(room, session, wav, duration_s, reason)

    collector = SileroUtteranceCollector(vad, on_utterance)
    session.utterance_collector = collector
    await collector.start()
    stream = rtc.AudioStream(track)
    try:
        async for event in stream:
            if session.muted:
                continue
            frame = event.frame
            floats, _ = frame_to_mono_floats(frame)
            if floats:
                session.peak_rms = max(session.peak_rms, _rms(floats))
            collector.push_frame(frame)
    finally:
        await collector.aclose()
        session.utterance_collector = None


async def _consume_audio_track(
    track: rtc.Track,
    room: rtc.Room,
    session: RoomSession,
) -> None:
    if voice_vad_mode() == "rms":
        await _consume_audio_track_rms(track, room, session)
        return
    vad = session.vad
    if vad is None:
        _log.error("Silero VAD missing on session — set VOICE_VAD=rms or fix worker prewarm")
        return
    await _consume_audio_track_silero(track, room, session, vad)


def _start_audio_consumer(
    track: rtc.Track,
    room: rtc.Room,
    session: RoomSession,
    participant: rtc.RemoteParticipant,
) -> None:
    if session.audio_consumer_started:
        return
    session.audio_consumer_started = True
    _log.info("consuming audio track from %s (vad=%s)", participant.identity, voice_vad_mode())
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
    if voice_vad_mode() == "silero":
        session.vad = ctx.proc.userdata.get("vad")
        if session.vad is None:
            _log.warning("Silero VAD not in proc.userdata; loading in-process")
            session.vad = load_silero_vad()

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
    _log.info(
        "agent joined room %s (vad=%s colab speech=%s)",
        room.name,
        voice_vad_mode(),
        "on" if speech_enabled() else "OFF — set COLAB_INFERENCE_BASE_URL",
    )
    _attach_existing_audio(room, session)


def main() -> None:
    if cli is None:
        raise RuntimeError("Install livekit-agents to run the worker")
    opts = WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm)
    cli.run_app(opts)


if __name__ == "__main__":
    main()
