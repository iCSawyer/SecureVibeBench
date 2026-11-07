from securevibebench_evaluation.redaction import redact_artifacts


def test_credentials_across_chunks_and_json_escapes_are_removed(tmp_path):
    import json
    secret = 'credential-"with-escapes-123'
    path = tmp_path / 'native.log'
    raw = b'x' * (1024 * 1024 - 5) + secret.encode() + b'\n' + json.dumps({'key': secret}).encode()
    path.write_bytes(raw)
    assert redact_artifacts(tmp_path, {'OPENROUTER_API_KEY': secret}) == ['native.log']
    result = path.read_bytes()
    assert secret.encode() not in result
    assert json.dumps(secret)[1:-1].encode() not in result
    assert result.count(b'[REDACTED_CREDENTIAL]') == 2
    assert redact_artifacts(tmp_path, {'OPENROUTER_API_KEY': secret}) == []


def test_redaction_keeps_external_symlinks_and_other_values(tmp_path):
    root = tmp_path / 'run'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.write_text('credential-12345678')
    (root / 'linked.log').symlink_to(outside)
    (root / 'native.log').write_text('Keep this log and credential-12345678')
    assert redact_artifacts(root, {'NORMAL_VALUE': 'credential-12345678'}) == []
    assert redact_artifacts(root, {'MODEL_API_KEY': 'credential-12345678'}) == ['native.log']
    assert outside.read_text() == 'credential-12345678'
    assert (root / 'native.log').read_text() == 'Keep this log and [REDACTED_CREDENTIAL]'
