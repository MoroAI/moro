import json

import pytest

from moro.config.models import MoroConfig
from moro.core.hashing import config_snapshot_hash, matches_config_snapshot, sha256_text


@pytest.mark.parametrize("rate", [2e-4, 1e-5, 1e-6, 1e-8])
def test_legacy_training_hash_matches_saved_snapshot(rate):
    cfg = MoroConfig.model_validate({
        "project": {"name": "مشروع"}, "dataset": {"source": "data/é.jsonl"},
        "model": {"name": "local"}, "training": {"learning_rate": rate},
    })
    assert matches_config_snapshot(cfg.model_dump_json(indent=2), sha256_text(cfg.model_dump_json()))


def test_versioned_hash_ignores_layout_and_key_order():
    text = '{"name":"é", "learning_rate":0.00001, "seed":42}'
    reformatted = json.dumps(dict(reversed(list(json.loads(text).items()))), indent=4)
    digest = config_snapshot_hash(text)
    assert digest.startswith("config-json-v1:")
    assert matches_config_snapshot(reformatted, digest)
    assert not matches_config_snapshot(text.replace("42", "43"), digest)


def test_legacy_hash_does_not_add_new_schema_defaults():
    text = '{"release":{"require":{"safety_pass":false}}}'
    assert matches_config_snapshot(text, sha256_text(text))


@pytest.mark.parametrize("text", ['{"x":NaN}', '{"x":Infinity}', '{"x":1,"x":2}', '[]'])
def test_invalid_snapshot_content_rejected(text):
    with pytest.raises(ValueError):
        config_snapshot_hash(text)


def test_unknown_hash_version_is_not_accepted():
    assert not matches_config_snapshot('{"x":1}', "config-json-v99:123")
