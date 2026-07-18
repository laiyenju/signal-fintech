import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from newsroom import source_activity

def test_source_activity_counts_silent_and_dropped():
    feeds = [{"name": "A", "scope": "tw"}, {"name": "Silent", "scope": "tw"}]
    raw = [{"source": "A", "scope": "tw"}, {"source": "A", "scope": "tw"}]
    meta = {"tw": {"scoredPool": [
                {"source": "A", "decision": "cover"},
                {"source": "A", "decision": "dropped"}]},
            "global": {"scoredPool": []}}
    got = {s["name"]: s for s in source_activity(raw, meta, feeds)}
    assert got["A"]["windowItems"] == 2
    assert got["A"]["contributed"] == 1          # dropped 不算
    assert got["Silent"]["windowItems"] == 0     # 沒更新的源仍列出
    assert got["Silent"]["contributed"] == 0
