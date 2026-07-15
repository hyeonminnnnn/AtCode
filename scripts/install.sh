#!/usr/bin/env bash
set -euo pipefail

ATCODE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
LOCAL_BIN="${HOME}/.local/bin"
COMMAND_PATH="${LOCAL_BIN}/atcode"
CODEX_INSTALL_URL="https://chatgpt.com/codex/install.sh"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
CODEX_PATH=""
PATH_PERSISTED=1

pass() {
  printf '[PASS] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1" >&2
  return 1
}

usage() {
  printf 'Usage: bash scripts/install.sh [--launcher-only]\n' >&2
}

confirm() {
  local prompt="$1"
  local answer

  [[ -t 0 ]] || return 1
  read -r -p "${prompt} [y/N] " answer
  case "${answer}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

check_platform() {
  local kernel
  kernel="$(uname -s 2>/dev/null || true)"
  if [[ "${kernel}" != "Linux" ]]; then
    fail "AtCode는 WSL2 또는 Linux에서 설치해야 합니다."
    printf 'PowerShell에서 실행: wsl -d Ubuntu\n' >&2
    return 1
  fi
  pass "WSL/Linux 환경"
}

check_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    fail "Python 3.11 이상이 필요합니다."
    printf 'Ubuntu 안내: sudo apt install python3\n' >&2
    return 1
  fi
  if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "Python 3.11 이상이 필요합니다."
    printf '현재 버전: %s\n' "$(python3 --version 2>&1 || true)" >&2
    return 1
  fi
  pass "$(python3 --version 2>&1)"
}

install_apt_package() {
  local package="$1"

  if ! command -v apt-get >/dev/null 2>&1 || ! command -v sudo >/dev/null 2>&1; then
    fail "${package} 자동 설치는 Ubuntu/Debian 환경에서만 지원합니다."
    return 1
  fi
  warn "시스템 패키지 ${package}가 필요합니다."
  printf '실행할 명령: sudo apt-get update && sudo apt-get install -y %s\n' "${package}"
  if ! confirm "${package}를 설치할까요?"; then
    fail "설치를 중단했습니다. 위 명령을 실행한 뒤 다시 시도하세요."
    return 1
  fi
  sudo apt-get update
  sudo apt-get install -y "${package}"
}

ensure_tmux() {
  if command -v tmux >/dev/null 2>&1 && tmux -V >/dev/null 2>&1; then
    pass "$(tmux -V)"
    return 0
  fi
  install_apt_package "tmux" || return 1
  if ! command -v tmux >/dev/null 2>&1 || ! tmux -V >/dev/null 2>&1; then
    fail "tmux 설치를 확인할 수 없습니다."
    return 1
  fi
  pass "$(tmux -V)"
}

is_windows_mounted_path() {
  [[ "$1" =~ ^/mnt/[[:alpha:]]/ ]]
}

find_working_codex() {
  local path
  path="$(command -v codex 2>/dev/null || true)"
  if [[ -z "${path}" ]]; then
    return 1
  fi
  if is_windows_mounted_path "${path}"; then
    warn "Windows용 Codex가 감지되었습니다: ${path}"
    return 1
  fi
  if ! "${path}" --version >/dev/null 2>&1; then
    warn "Codex 명령을 실행할 수 없습니다: ${path}"
    return 1
  fi
  CODEX_PATH="${path}"
  pass "Codex: ${CODEX_PATH}"
}

ensure_codex() {
  local installer

  if find_working_codex; then
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    install_apt_package "curl" || return 1
  fi
  warn "WSL/Linux용 Codex가 필요합니다."
  printf '공식 설치 URL: %s\n' "${CODEX_INSTALL_URL}"
  if ! confirm "공식 Codex 설치 스크립트를 실행할까요?"; then
    fail "Codex 설치를 중단했습니다."
    return 1
  fi

  installer="$(mktemp)"
  if ! curl -fsSL "${CODEX_INSTALL_URL}" -o "${installer}"; then
    rm -f -- "${installer}"
    fail "Codex 설치 스크립트를 내려받지 못했습니다."
    return 1
  fi
  if ! bash "${installer}"; then
    rm -f -- "${installer}"
    fail "Codex 설치가 완료되지 않았습니다."
    return 1
  fi
  rm -f -- "${installer}"
  hash -r

  if ! find_working_codex; then
    fail "설치 후에도 WSL/Linux용 Codex를 실행할 수 없습니다."
    return 1
  fi
}

ensure_shell_path() {
  local bashrc="${HOME}/.bashrc"

  case ":${PATH}:" in
    *":${LOCAL_BIN}:"*) ;;
    *) export PATH="${LOCAL_BIN}:${PATH}" ;;
  esac

  if [[ -f "${bashrc}" ]] && grep -Fqx -- "${PATH_LINE}" "${bashrc}"; then
    pass "PATH 설정: ${LOCAL_BIN}"
    return 0
  fi

  warn "새 터미널에서도 atcode와 codex를 찾도록 PATH 설정이 필요합니다."
  printf '추가할 줄: %s\n' "${PATH_LINE}"
  if ! confirm "${bashrc}에 PATH 설정을 추가할까요?"; then
    PATH_PERSISTED=0
    warn "PATH 영구 설정을 건너뛰었습니다."
    return 0
  fi
  printf '\n%s\n' "${PATH_LINE}" >> "${bashrc}"
  pass "PATH 설정 저장: ${bashrc}"
}

ensure_codex_login() {
  if "${CODEX_PATH}" login status >/dev/null 2>&1; then
    pass "Codex 로그인 확인"
    return 0
  fi

  warn "Codex 로그인이 필요합니다."
  if ! confirm "codex login을 실행할까요?"; then
    fail "로그인을 중단했습니다. 나중에 codex login을 실행하세요."
    return 1
  fi
  if ! "${CODEX_PATH}" login; then
    fail "Codex 로그인에 실패했습니다."
    printf '대안 명령: codex login --device-auth\n' >&2
    return 1
  fi
  if ! "${CODEX_PATH}" login status >/dev/null 2>&1; then
    fail "Codex 로그인 상태를 확인할 수 없습니다."
    return 1
  fi
  pass "Codex 로그인 확인"
}

install_launcher() {
  local temporary

  mkdir -p -- "${LOCAL_BIN}"
  temporary="${COMMAND_PATH}.tmp.$$"
  printf '#!/usr/bin/env bash\nexec %q "$@"\n' \
    "${ATCODE_ROOT}/bin/atcode" > "${temporary}"
  chmod 755 -- "${temporary}"
  mv -f -- "${temporary}" "${COMMAND_PATH}"
  pass "AtCode launcher: ${COMMAND_PATH}"
}

run_doctor() {
  if ! "${COMMAND_PATH}" doctor; then
    fail "atcode doctor에서 실패 항목을 확인하세요."
    return 1
  fi
}

main() {
  if [[ $# -eq 1 && "$1" == "--launcher-only" ]]; then
    install_launcher
    return 0
  fi
  if [[ $# -ne 0 ]]; then
    usage
    return 2
  fi

  printf 'AtCode WSL/Linux 설치를 시작합니다.\n'
  check_platform
  check_python
  ensure_tmux
  ensure_shell_path
  ensure_codex
  ensure_codex_login
  install_launcher
  run_doctor

  printf '\n설치가 완료되었습니다. 작업 프로젝트에서 실행하세요.\n'
  if [[ "${PATH_PERSISTED}" -eq 1 ]]; then
    printf '현재 터미널에 PATH 적용: source "$HOME/.bashrc"\n'
  else
    printf '현재 셸에서 먼저 실행: export PATH="$HOME/.local/bin:$PATH"\n'
  fi
  printf '  atcode init\n  atcode start\n  atcode attach\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
