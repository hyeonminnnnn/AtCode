#!/usr/bin/env bash
set -euo pipefail

ATCODE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTALL_DIR="${HOME}/.local/bin"
COMMAND_PATH="${INSTALL_DIR}/atcode"

mkdir -p -- "${INSTALL_DIR}"
printf '#!/usr/bin/env bash\nexec %q "$@"\n' \
  "${ATCODE_ROOT}/bin/atcode" > "${COMMAND_PATH}"
chmod 755 -- "${COMMAND_PATH}"

printf 'AtCode 설치 완료: %s\n' "${COMMAND_PATH}"
case ":${PATH}:" in
  *":${INSTALL_DIR}:"*) ;;
  *) printf 'PATH에 다음 경로를 추가하세요: %s\n' "${INSTALL_DIR}" ;;
esac
