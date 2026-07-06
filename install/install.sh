#!/usr/bin/env bash
# HomeCloud CLI installer — curl -sSL https://install.homecloud.dev | bash
set -euo pipefail

INSTALL_BASE="${HOMECLOUD_INSTALL_URL:-https://homecloud-cli.so.holab.abrdns.com/releases}"
VERSION="${HOMECLOUD_VERSION:-latest}"
INSTALL_DIR="${HOMECLOUD_INSTALL_DIR:-/usr/local/bin}"
BINARY_NAME="homecloud"

detect_platform() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "${arch}" in
    x86_64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;;
  esac
  case "${os}" in
    linux) echo "linux-${arch}" ;;
    darwin) echo "darwin-${arch}" ;;
    *) echo "unsupported OS: ${os}. Use Windows installer or direct download." >&2; exit 1 ;;
  esac
}

PLATFORM="$(detect_platform)"
ARTIFACT="homecloud-${PLATFORM}"
URL="${INSTALL_BASE}/${VERSION}/${ARTIFACT}"
TMP="$(mktemp)"
CHECKSUM_URL="${URL}.sha256"

cleanup() { rm -f "${TMP}" "${TMP}.sha256" 2>/dev/null || true; }
trap cleanup EXIT

echo "Installing HomeCloud CLI (${VERSION}, ${PLATFORM})..."

if ! curl -fsSL "${URL}" -o "${TMP}"; then
  echo "Download failed: ${URL}" >&2
  exit 1
fi

if curl -fsSL "${CHECKSUM_URL}" -o "${TMP}.sha256" 2>/dev/null; then
  if command -v sha256sum >/dev/null 2>&1; then
    expected="$(awk '{print $1}' "${TMP}.sha256")"
    actual="$(sha256sum "${TMP}" | awk '{print $1}')"
  else
    expected="$(awk '{print $1}' "${TMP}.sha256")"
    actual="$(shasum -a 256 "${TMP}" | awk '{print $1}')"
  fi
  if [[ "${expected}" != "${actual}" ]]; then
    echo "Checksum mismatch — aborting." >&2
    exit 1
  fi
fi

chmod +x "${TMP}"

if [[ -w "${INSTALL_DIR}" ]]; then
  mv "${TMP}" "${INSTALL_DIR}/${BINARY_NAME}"
else
  sudo mv "${TMP}" "${INSTALL_DIR}/${BINARY_NAME}"
fi

echo "Installed: ${INSTALL_DIR}/${BINARY_NAME}"
"${INSTALL_DIR}/${BINARY_NAME}" version
