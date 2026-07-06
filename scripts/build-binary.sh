#!/usr/bin/env bash
# Build a single-file homecloud binary for the current OS/arch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist"
VERSION="$(python -c "import importlib.util; spec=importlib.util.spec_from_file_location('v','${ROOT}/homecloud_cli/__init__.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.__version__)")"

if [[ ! -f "${ROOT}/homecloud_core/__init__.py" || ! -f "${ROOT}/homecloud_sdk/__init__.py" ]]; then
  echo "Vendored SDK packages missing (homecloud_core, homecloud_sdk)." >&2
  exit 1
fi

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "unsupported arch: ${ARCH}" >&2; exit 1 ;;
esac

case "${OS}" in
  linux|darwin) ;;
  *) echo "unsupported os: ${OS}" >&2; exit 1 ;;
esac

ARTIFACT="homecloud-${OS}-${ARCH}"
if [[ "${OS}" == "darwin" ]]; then
  ARTIFACT="homecloud-darwin-${ARCH}"
fi

echo "Building ${ARTIFACT} (v${VERSION})..."

export HOMECLOUD_SDK_ROOT="${ROOT}"
python -m pip install -q -e "${ROOT}[build]"
rm -rf "${DIST}/build" "${DIST}/${ARTIFACT}" "${DIST}/${ARTIFACT}.sha256"

pyinstaller --noconfirm --clean --distpath "${DIST}" --workpath "${DIST}/build" "${ROOT}/homecloud.spec"

mv "${DIST}/homecloud" "${DIST}/${ARTIFACT}"
chmod +x "${DIST}/${ARTIFACT}"

if command -v strip >/dev/null 2>&1; then
  strip "${DIST}/${ARTIFACT}" 2>/dev/null || true
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${DIST}/${ARTIFACT}" > "${DIST}/${ARTIFACT}.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "${DIST}/${ARTIFACT}" > "${DIST}/${ARTIFACT}.sha256"
fi

echo "Built: ${DIST}/${ARTIFACT}"
ls -lh "${DIST}/${ARTIFACT}"
