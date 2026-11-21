import asyncio

import pytest
from voice_agent.tts_pipeline import TtsPipeline, extract_segments


def test_extract_segments_sentence_boundary():
    segs, rest = extract_segments("First sentence. Second start", flush=False)
    assert segs == ["First sentence."]
    assert rest == "Second start"


def test_extract_segments_flush_tail():
    segs, rest = extract_segments("Short tail", flush=True)
    assert segs == ["Short tail"]
    assert rest == ""


@pytest.mark.asyncio
async def test_pipeline_synth_before_stream_done():
    synth_calls: list[str] = []
    play_calls: list[bytes] = []

    async def synth(text: str) -> bytes:
        synth_calls.append(text)
        await asyncio.sleep(0.01)
        return text.encode()

    async def play(_room, _session, wav: bytes) -> None:
        play_calls.append(wav)

    cancel = asyncio.Event()
    pipeline = TtsPipeline(
        synthesize=synth,
        play_wav=play,
        cancel_event=cancel,
        session=object(),
        room=object(),
    )
    await pipeline.start()
    pipeline.feed_token("Hello there. ")
    pipeline.feed_token("More words follow.")
    await pipeline.finish()
    assert synth_calls
    assert play_calls
