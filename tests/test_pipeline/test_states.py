from backend.pipeline.states import GateStatus, PaperState, Phase


def test_state_default_values():
    state = PaperState(task_id="abc", topic="测试主题")
    assert state.current_phase == Phase.SCOPING
    assert state.literature == []
    assert state.sections == {}


def test_gate_phases_full_auto():
    state = PaperState(task_id="abc", topic="t", collab_mode="full_auto")
    assert state.gate_phases == set()


def test_gate_phases_key_gates():
    """key_gates pauses at every phase — the partial-gating modes were dropped."""
    state = PaperState(task_id="abc", topic="t", collab_mode="key_gates")
    assert state.gate_phases == set(Phase)


def test_gate_phases_unknown_mode_gates_nothing():
    state = PaperState(task_id="abc", topic="t", collab_mode="phase_sync")
    assert state.gate_phases == set()


def test_errors_accumulate():
    state = PaperState(task_id="abc", topic="t", errors=["err1"])
    assert "err1" in state.errors


def test_gate_status_defaults_to_skipped():
    state = PaperState(task_id="abc", topic="t")
    assert state.gate_status == GateStatus.SKIPPED
