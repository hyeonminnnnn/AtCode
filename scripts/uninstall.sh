#!/usr/bin/env bash
set -euo pipefail

ATCODE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
COMMAND_PATH="${HOME}/.local/bin/atcode"
PURGE_DATA=false

if [[ "${1:-}" == "--purge-data" ]]; then
  PURGE_DATA=true
elif [[ $# -gt 0 ]]; then
  printf '알 수 없는 옵션: %s\n' "$1" >&2
  exit 2
fi

rm -f -- "${COMMAND_PATH}"
printf 'AtCode 명령 제거 완료: %s\n' "${COMMAND_PATH}"

if [[ "${PURGE_DATA}" == true ]]; then
  RUNTIME_HOME="${ATCODE_HOME:-${ATCODE_ROOT}/data}"
  if [[ -z "${RUNTIME_HOME}" || "${RUNTIME_HOME}" == "/" ]]; then
    printf '안전하지 않은 ATCODE_HOME은 삭제할 수 없습니다: %s\n' "${RUNTIME_HOME}" >&2
    exit 2
  fi
  printf 'Runtime 데이터 삭제 대상: %s\n' "${RUNTIME_HOME}"
  printf '삭제하려면 DELETE를 입력하세요: '
  read -r CONFIRMATION
  if [[ "${CONFIRMATION}" != "DELETE" ]]; then
    printf 'Runtime 데이터 삭제를 취소했습니다.\n'
    exit 0
  fi
  rm -rf -- "${RUNTIME_HOME}"
  printf 'Runtime 데이터 삭제 완료: %s\n' "${RUNTIME_HOME}"
else
  printf 'Runtime 데이터는 보존했습니다: %s\n' "${ATCODE_HOME:-${ATCODE_ROOT}/data}"
fi
