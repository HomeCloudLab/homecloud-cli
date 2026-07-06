#!/usr/bin/env bash
# Upload built binaries to S3-compatible storage (MinIO / AWS S3).
# Requires: mc (MinIO client) or aws CLI configured.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist"
VERSION="${1:?usage: upload-release.sh <version>}"
BUCKET="${HOMECLOUD_CLI_BUCKET:-homecloud-cli}"
ENDPOINT="${HOMECLOUD_S3_ENDPOINT:-}"

if [[ ! -d "${DIST}" ]]; then
  echo "dist/ not found — run build-binary first" >&2
  exit 1
fi

upload_mc() {
  local target="$1"
  mc cp "${DIST}/${target}" "local/${BUCKET}/releases/v${VERSION}/${target}"
  mc cp "${DIST}/${target}.sha256" "local/${BUCKET}/releases/v${VERSION}/${target}.sha256" 2>/dev/null || true
  mc cp "${DIST}/${target}" "local/${BUCKET}/releases/latest/${target}"
}

if command -v mc >/dev/null 2>&1 && [[ -n "${ENDPOINT}" ]]; then
  mc alias set local "${ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" 2>/dev/null || true
  for f in "${DIST}"/homecloud-*; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
    [[ "$base" == *.sha256 ]] && continue
    upload_mc "$base"
  done
  echo "Uploaded to s3://${BUCKET}/releases/v${VERSION}/"
elif command -v aws >/dev/null 2>&1; then
  aws s3 sync "${DIST}/" "s3://${BUCKET}/releases/v${VERSION}/" --exclude "*.sha256"
  aws s3 sync "${DIST}/" "s3://${BUCKET}/releases/latest/" --exclude "*.sha256"
  echo "Uploaded to s3://${BUCKET}/releases/v${VERSION}/"
else
  echo "No mc/aws CLI — skipping S3 upload. Artifacts in ${DIST}/" >&2
fi
