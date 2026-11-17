from app.v2.services.checkpoints import JsonCheckpointStore


def test_save_load(tmp_path):
    cp = JsonCheckpointStore(str(tmp_path))
    cp.save("thread-1", {"worker": "conversation"})
    loaded = cp.load("thread-1")
    assert loaded["worker"] == "conversation"
