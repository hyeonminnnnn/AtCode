# Tmux Bracketed Paste Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Ctrl+b Enter`로 전달한 인계가 Codex의 paste-burst 대기 상태에 머물지 않고 즉시 제출되게 합니다.

**Architecture:** Tmux Backend가 실제 터미널 붙여넣기 의미를 보존하도록 `paste-buffer -p`를 사용합니다. Adapter와 Workflow 인터페이스는 변경하지 않으며, 임의 지연이나 `Esc` 입력도 추가하지 않습니다.

**Tech Stack:** Python 3.11+, pytest, tmux 3.4+

## Global Constraints

- Runtime 데이터는 `ATCODE_HOME`에만 저장합니다.
- 작업 대상 프로젝트에 AtCode 관리 파일을 만들지 않습니다.
- Application은 tmux 명령을 알지 않으며 Adapter는 CLI 실행 책임만 유지합니다.
- 전달 본문은 Shell 명령 인자로 삽입하지 않습니다.

---

### Task 1: Bracketed paste로 인계 전달

**Files:**
- Modify: `tests/unit/test_tmux_backend.py`
- Modify: `src/atcode/infrastructure/tmux_backend.py`

**Interfaces:**
- Consumes: `TmuxBackend.deliver_text(session_name: str, role: Role, text: str) -> None`
- Produces: 기존 인터페이스를 유지하면서 tmux `paste-buffer -p` 명령을 실행합니다.

- [ ] **Step 1: 실패 테스트를 작성합니다.**

`test_deliver_text_uses_tmux_buffer_stdin_and_never_shell_content`에서 Target Pane의
`paste-buffer` 호출에 `-p`가 포함되는지 검증합니다.

```python
paste_call = next(call for call in runner.calls if "paste-buffer" in call.argv)
assert "-p" in paste_call.argv
assert "%2" in paste_call.argv
```

- [ ] **Step 2: 테스트가 올바른 이유로 실패하는지 확인합니다.**

```bash
python -m pytest -q tests/unit/test_tmux_backend.py::test_deliver_text_uses_tmux_buffer_stdin_and_never_shell_content
```

예상 결과: 현재 `paste-buffer` 호출에 `-p`가 없어 assertion이 실패합니다.

- [ ] **Step 3: 최소 구현을 적용합니다.**

`TmuxBackend.deliver_text()`의 `paste-buffer` 인자에 `-p`를 추가합니다.

```python
(
    "tmux",
    "paste-buffer",
    "-p",
    "-d",
    "-b",
    "atcode-transfer",
    "-t",
    endpoint.pane,
)
```

- [ ] **Step 4: 관련 테스트와 전체 회귀 테스트를 실행합니다.**

```bash
python -m pytest -q tests/unit/test_tmux_backend.py
python -m pytest -q
python -m compileall -q src tests
```

예상 결과: 관련 테스트와 지원 환경의 전체 테스트가 모두 통과합니다.

- [ ] **Step 5: WSL에서 실제 전달을 확인합니다.**

기존 Session에서 Developer 또는 Reviewer가 handoff를 완성한 뒤 `Ctrl+b Enter`를
한 번 누릅니다. 대상 Codex Pane에서 `Esc`나 수동 `Enter` 없이 전달 내용이 즉시
제출되어 작업이 시작되어야 합니다.

- [ ] **Step 6: 변경을 커밋합니다.**

```bash
git add docs/superpowers/specs/2026-07-15-phase2-relay-workflow-design.md \
  docs/superpowers/plans/2026-07-20-tmux-bracketed-paste-fix.md \
  tests/unit/test_tmux_backend.py \
  src/atcode/infrastructure/tmux_backend.py
git commit -m "fix: submit relayed prompts as bracketed paste"
```
