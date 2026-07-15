# Codex 기본 배정과 모델 중립 역할 Prompt 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1의 기본 역할 Adapter를 모두 Codex로 통일하고, 특정 모델의 스킬 호출 없이 역할별 작업 방법을 수행하는 상세 Prompt를 제공한다.

**Architecture:** 기존 ConfigurationService의 내장 기본값과 Markdown Prompt 템플릿만 변경한다. Adapter Registry, Prompt Renderer, CLI 인터페이스는 유지하며 테스트로 기본값과 Prompt 계약을 고정한다.

**Tech Stack:** Python 3.11+, pytest, Markdown, Bash

## Global Constraints

- 기본 역할은 `pm`, `developer`, `reviewer`, `tester`, `docs` 다섯 개다.
- 기본 Adapter는 다섯 역할 모두 `codex`다.
- Claude, Gemini, Shell Adapter와 역할별 override 기능은 제거하지 않는다.
- Prompt에는 특정 모델의 스킬 이름이나 호출 문법을 넣지 않는다.
- 대상 프로젝트에는 AtCode 설정, 상태, Workspace, 로그를 생성하지 않는다.
- Agent Relay, Task Queue, 자동 Workflow는 구현하지 않는다.
- `.env`, `.env.local`은 읽거나 수정하지 않는다.

---

### Task 1: 기본 Adapter를 Codex로 통일

**Files:**
- Modify: `tests/unit/test_configuration.py`
- Modify: `src/atcode/application/configuration.py`

**Interfaces:**
- Consumes: `ConfigurationService.effective(project: Project | None) -> RuntimeConfig`
- Produces: override가 없을 때 모든 `Role`을 `RoleAssignment("codex")`로 반환하는 기본 설정

- [ ] **Step 1: 기본 역할 전체가 Codex인지 확인하는 실패 테스트 작성**

```python
def test_all_default_roles_use_codex(tmp_path: Path) -> None:
    service, _store = make_service(tmp_path)

    config = service.effective(None)

    assert {role: config.roles[role].adapter for role in Role} == {
        role: "codex" for role in Role
    }
```

- [ ] **Step 2: 테스트가 현재 혼합 Adapter 기본값 때문에 실패하는지 확인**

Run: `python -m pytest -q tests/unit/test_configuration.py::test_all_default_roles_use_codex`

Expected: FAIL. PM, Reviewer, Docs 값이 각각 `claude`, `gemini`, `claude`다.

- [ ] **Step 3: ConfigurationService 내장 기본값 변경**

```python
"roles": {
    "pm": {"adapter": "codex"},
    "developer": {"adapter": "codex"},
    "reviewer": {"adapter": "codex"},
    "tester": {"adapter": "codex"},
    "docs": {"adapter": "codex"},
},
```

- [ ] **Step 4: 설정 테스트 전체 실행**

Run: `python -m pytest -q tests/unit/test_configuration.py`

Expected: 모든 테스트 PASS. 전역·프로젝트 override 테스트도 유지된다.

- [ ] **Step 5: 설정 변경 커밋**

```bash
git add src/atcode/application/configuration.py tests/unit/test_configuration.py
git commit -m "feat: default all roles to codex"
```

---

### Task 2: 역할 Prompt 계약과 상세 절차 구현

**Files:**
- Modify: `tests/unit/test_prompts.py`
- Modify: `prompts/pm.md`
- Modify: `prompts/developer.md`
- Modify: `prompts/reviewer.md`
- Modify: `prompts/tester.md`
- Modify: `prompts/docs.md`

**Interfaces:**
- Consumes: `PromptRenderer.render(project: Project, role: Role) -> RenderedPrompt`
- Produces: 기존 다섯 토큰만 사용하는 역할별 Markdown Prompt

- [ ] **Step 1: Prompt 공통 계약 실패 테스트 작성**

```python
@pytest.mark.parametrize("role", list(Role))
def test_role_template_has_operating_contract(role: Role) -> None:
    text = (REPO_ROOT / "prompts" / f"{role.value}.md").read_text(
        encoding="utf-8"
    )

    for heading in ("## 핵심 책임", "## 작업 방법", "## 산출물", "## 완료 조건", "## 경계"):
        assert heading in text
    assert "{{PROJECT_ROOT}}" in text
    assert "{{ATCODE_HOME}}" in text
    assert "Phase 1" in text
```

역할별 방법론도 별도 assertion으로 고정한다.

```python
def test_role_templates_embed_model_neutral_methods() -> None:
    templates = {
        role: (REPO_ROOT / "prompts" / f"{role.value}.md").read_text(encoding="utf-8")
        for role in Role
    }

    assert "가정" in templates[Role.PM] and "완료 조건" in templates[Role.PM]
    assert "실패하는 테스트" in templates[Role.DEVELOPER]
    assert "과설계" in templates[Role.REVIEWER]
    assert "미검증" in templates[Role.TESTER]
    assert "사실, 주장, 수치" in templates[Role.DOCS]
    assert "{{ATCODE_HOME}}/projects/{{PROJECT_ID}}/workspace" in templates[Role.DOCS]
    assert not any("$" in text for text in templates.values())
```

- [ ] **Step 2: 현재 간결한 Prompt가 계약 테스트에 실패하는지 확인**

Run: `python -m pytest -q tests/unit/test_prompts.py`

Expected: 새 공통 제목과 역할별 방법론 assertion이 FAIL한다.

- [ ] **Step 3: PM Prompt 확장**

다음 내용을 정확한 제목 아래 작성한다.

```text
# PM
작업 문맥: 프로젝트 이름·ID·루트·ATCODE_HOME
## 핵심 책임: 요구사항, 가정, 범위, 완료 조건, 작업 분할
## 작업 방법: 가정 공개 → 명세 → 사용자 승인 → 의존성 기반 작업 분할 → 검증 정의
## 산출물: 목표·범위·제외 범위·가정·완료 조건·작업 순서·검증 명령·주의사항
## 완료 조건: 모호성 해소, 검증 가능한 완료 조건, 구현 가능한 작업 단위
## 경계: 승인 전 구현 금지, 자동 전달 금지, AtCode 관리 파일 생성 금지
```

- [ ] **Step 4: Developer Prompt 확장**

```text
# Developer
작업 문맥: 프로젝트 이름·ID·루트·ATCODE_HOME
## 핵심 책임: 승인된 명세 구현, 기존 패턴 준수, 변경·검증 보고
## 작업 방법: 조사 → 실패 테스트 → 최소 구현 → 관련 테스트 → 필요한 정리 → 전체 회귀
오류 발생 시: 재현 → 위치 좁히기 → 최소 사례 → 근본 원인 → 회귀 테스트
## 산출물: 구현 요약·변경 파일·설계 판단·검증·남은 위험·Reviewer 확인 사항
## 완료 조건: 완료 조건 충족, 관련/회귀 테스트 통과, 범위 밖 변경 없음
## 경계: 임의 리팩터링·테스트 삭제·자동 commit/push·AtCode 관리 파일 금지
```

- [ ] **Step 5: Reviewer Prompt 확장**

```text
# Reviewer
작업 문맥: 프로젝트 이름·ID·루트·ATCODE_HOME
## 핵심 책임: 명세 충족, 정확성, 회귀, 오류 처리, 보안, 테스트, 유지보수성
## 작업 방법: 일반 품질 검토 후 별도 과설계 검토
과설계 검토: 불필요한 추상화·미사용 확장성·표준 기능 재구현·과도한 계층과 단순 대안
## 산출물: 심각도·파일 위치·문제·영향·근거·권장 수정, 과설계 결과 분리
## 완료 조건: 재현 가능한 중요 결함 우선, 억지 지적 없음
## 경계: 코드 수정 금지, 취향을 결함으로 보고 금지, 자동 전달 금지
```

- [ ] **Step 6: Tester Prompt 확장**

```text
# Tester
작업 문맥: 프로젝트 이름·ID·루트·ATCODE_HOME
## 핵심 책임: 완료 조건을 정상·오류·경계·회귀 시나리오로 변환
## 작업 방법: 기존 도구 우선, 실제 명령 실행, 실패 증거 보존, 브라우저면 화면·DOM·Console·Network·접근성 확인
## 산출물: 환경·명령·통과·실패·재현 절차·미검증·출시 판단
## 완료 조건: 실행한 검증과 미검증 항목 구분, 실패 재현 가능
## 경계: 제품 코드 임의 수정·실패 은폐·실행하지 않은 검증 보고 금지
```

- [ ] **Step 7: Docs Prompt 확장**

```text
# Docs
작업 문맥: 프로젝트 이름·ID·루트·ATCODE_HOME
## 핵심 책임: 명세·구현·검증 대조, 실행 가능한 명령·경로·제약 문서화
## 작업 방법: 결정 이유 중심 기록, 중요한 결정만 ADR, 한국어 번역투·기계적 병렬·과도한 접속사 완화
윤문 불변 조건: 사실·주장·수치·날짜·고유명사·명령·경로 보존
중간 자료 경로: ATCODE_HOME/projects/PROJECT_ID/workspace
## 산출물: 문서 요약·변경 파일·실행 방법·제약·검증 근거
## 완료 조건: 구현·검증된 사실만 포함, 명령과 경로 정확
## 경계: 요청된 경우만 프로젝트 문서 수정, 불필요한 ADR·AtCode 관리 파일 금지
```

- [ ] **Step 8: Prompt 테스트와 무오염 통합 테스트 실행**

Run: `python -m pytest -q tests/unit/test_prompts.py tests/integration/test_no_target_artifacts.py`

Expected: 모두 PASS. 렌더링 파일은 `ATCODE_HOME/projects/<id>/workspace/prompts` 아래에만 존재한다.

- [ ] **Step 9: Prompt 변경 커밋**

```bash
git add prompts tests/unit/test_prompts.py
git commit -m "feat: expand model neutral role prompts"
```

---

### Task 3: README와 전체 검증

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1의 Codex 기본값과 Task 2의 역할 Prompt 정책
- Produces: 실제 기본 동작과 일치하는 사용자 문서

- [ ] **Step 1: README 기본 Adapter 표 갱신**

```text
pm        = codex
developer = codex
reviewer  = codex
tester    = codex
docs      = codex
```

바로 아래에 Claude, Gemini, Shell Adapter 지원은 유지되며 `atcode config set`으로 변경할 수 있다고 명시한다. 역할 Prompt는 모델별 스킬 호출이 아니라 모델 중립 작업 절차를 포함한다고 설명한다.

- [ ] **Step 2: 전체 검증 실행**

```bash
python -m pytest -q
python -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
```

Expected: 전체 pytest PASS, compileall exit 0, Bash syntax exit 0.

- [ ] **Step 3: 금지 기능과 whitespace 확인**

```bash
rg -n "send-keys|capture-pane" src
git diff --check
```

Expected: `rg` 결과 없음, `git diff --check` 결과 없음.

- [ ] **Step 4: 문서 변경 커밋**

```bash
git add README.md
git commit -m "docs: explain codex role defaults"
```

- [ ] **Step 5: 최종 상태 확인**

```bash
git status --short --branch
git log --oneline -5
```

Expected: `feature/phase1-runtime` 브랜치, 작업 트리 clean, 새 커밋 세 개가 최근 로그에 표시된다.
