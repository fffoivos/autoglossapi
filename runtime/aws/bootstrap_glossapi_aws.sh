#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOMATION_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

REPO_URL="${REPO_URL:-https://github.com/eellak/glossAPI}"
TARGET_DIR="${TARGET_DIR:-/opt/dlami/nvme/glossapi/glossAPI}"
TARGET_BRANCH="${TARGET_BRANCH:-development}"
INSTALL_SYSTEM_PACKAGES="${INSTALL_SYSTEM_PACKAGES:-1}"
DOWNLOAD_DEEPSEEK_MODEL="${DOWNLOAD_DEEPSEEK_MODEL:-0}"
EXPECT_GPU="${EXPECT_GPU:-1}"
NEEDS_RUST="${NEEDS_RUST:-1}"
NEEDS_CLEANER="${NEEDS_CLEANER:-1}"
NEEDS_DEEPSEEK_OCR="${NEEDS_DEEPSEEK_OCR:-0}"
BOOTSTRAP_MODE="${BOOTSTRAP_MODE:-provision}"
UPDATE_REPO="${UPDATE_REPO:-}"
ALLOW_DIRTY_REPO_UPDATE="${ALLOW_DIRTY_REPO_UPDATE:-0}"

log() {
  printf '[bootstrap_glossapi_aws] %s\n' "$*"
}

ensure_command() {
  local cmd="$1"
  local message="$2"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    log "${message}"
    exit 1
  fi
}

install_system_packages() {
  if [[ "${INSTALL_SYSTEM_PACKAGES}" != "1" ]]; then
    return
  fi
  ensure_command sudo "sudo is required to install system packages on this host"
  log "Installing system packages"
  sudo apt-get update
  sudo apt-get install -y \
    build-essential \
    curl \
    gcc \
    g++ \
    git \
    htop \
    jq \
    pkg-config \
    poppler-utils \
    python3 \
    python3-pip \
    python3-venv \
    tmux \
    unzip
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
  if command -v sudo >/dev/null 2>&1; then
    [[ -x "${HOME}/.local/bin/uv" ]] && sudo ln -sf "${HOME}/.local/bin/uv" /usr/local/bin/uv
    [[ -x "${HOME}/.local/bin/uvx" ]] && sudo ln -sf "${HOME}/.local/bin/uvx" /usr/local/bin/uvx
  fi
}

install_or_upgrade_rust_toolchain() {
  export PATH="${HOME}/.cargo/bin:${PATH}"
  if ! command -v rustup >/dev/null 2>&1; then
    log "Installing Rust toolchain manager"
    export RUSTUP_INIT_SKIP_PATH_CHECK=yes
    curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable
  fi
  log "Ensuring a current stable Rust toolchain"
  rustup toolchain install stable
  rustup default stable
}

ensure_maturin() {
  local runtime_python="$1"
  if "${runtime_python}" -m pip show maturin >/dev/null 2>&1; then
    return
  fi
  log "Installing maturin into the DeepSeek runtime"
  "${runtime_python}" -m pip install maturin
}

build_rust_extensions() {
  local runtime_python="$1"
  local venv_root
  venv_root="$(dirname "$(dirname "${runtime_python}")")"
  export VIRTUAL_ENV="${venv_root}"
  export PATH="${HOME}/.cargo/bin:$(dirname "${runtime_python}"):/usr/local/bin:${PATH}"
  ensure_maturin "${runtime_python}"
  log "Building glossapi_rs_cleaner"
  (cd "${TARGET_DIR}" && "${runtime_python}" -m maturin develop --release --manifest-path rust/glossapi_rs_cleaner/Cargo.toml)
  log "Building glossapi_rs_noise"
  (cd "${TARGET_DIR}" && "${runtime_python}" -m maturin develop --release --manifest-path rust/glossapi_rs_noise/Cargo.toml)
}

clone_or_update_repo() {
  local target_parent
  target_parent="$(dirname "${TARGET_DIR}")"
  mkdir -p "${target_parent}"

  if [[ ! -d "${TARGET_DIR}/.git" ]]; then
    if [[ "${BOOTSTRAP_MODE}" == "repair" ]]; then
      log "Repair mode requires an existing GlossAPI checkout at ${TARGET_DIR}"
      return 1
    fi
    log "Cloning GlossAPI into ${TARGET_DIR}"
    git clone "${REPO_URL}" "${TARGET_DIR}"
  fi

  local should_update="1"
  if [[ -n "${UPDATE_REPO}" ]]; then
    should_update="${UPDATE_REPO}"
  elif [[ "${BOOTSTRAP_MODE}" == "repair" ]]; then
    should_update="0"
  fi

  if [[ "${should_update}" != "1" ]]; then
    log "Skipping repo update for ${TARGET_DIR} (BOOTSTRAP_MODE=${BOOTSTRAP_MODE}, UPDATE_REPO=${UPDATE_REPO:-auto})"
    return 0
  fi

  if [[ "${ALLOW_DIRTY_REPO_UPDATE}" != "1" ]] && [[ -n "$(git -C "${TARGET_DIR}" status --short)" ]]; then
    log "Refusing to update a dirty checkout at ${TARGET_DIR}; set ALLOW_DIRTY_REPO_UPDATE=1 to override"
    return 1
  fi

  log "Updating GlossAPI checkout to ${TARGET_BRANCH}"
  git -C "${TARGET_DIR}" fetch origin
  git -C "${TARGET_DIR}" checkout "${TARGET_BRANCH}"
  git -C "${TARGET_DIR}" pull --ff-only origin "${TARGET_BRANCH}"
}

setup_deepseek_env() {
  log "Running GlossAPI DeepSeek setup"
  if [[ "${DOWNLOAD_DEEPSEEK_MODEL}" == "1" ]]; then
    (cd "${TARGET_DIR}" && bash dependency_setup/setup_deepseek_uv.sh --download-model)
  else
    (cd "${TARGET_DIR}" && bash dependency_setup/setup_deepseek_uv.sh)
  fi
}

resolve_runtime_python() {
  local candidate="${TARGET_DIR}/dependency_setup/deepseek_uv/dependency_setup/.venvs/deepseek/bin/python"
  if [[ -x "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  candidate="${TARGET_DIR}/dependency_setup/.venvs/deepseek/bin/python"
  if [[ -x "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  log "Could not locate the DeepSeek runtime python under ${TARGET_DIR}"
  return 1
}

run_readiness_check() {
  local runtime_python="$1"
  local check_args=(
    python3
    "${AUTOMATION_ROOT}/runtime/aws/check_glossapi_runtime.py"
    --repo "${TARGET_DIR}"
    --python "${runtime_python}"
    --strict
  )
  if [[ "${NEEDS_RUST}" == "1" ]]; then
    check_args+=(--needs-rust)
  fi
  if [[ "${NEEDS_CLEANER}" == "1" ]]; then
    check_args+=(--needs-cleaner)
  fi
  if [[ "${EXPECT_GPU}" == "1" ]]; then
    check_args+=(--expect-gpu)
  fi
  if [[ "${NEEDS_DEEPSEEK_OCR}" == "1" ]]; then
    check_args+=(--needs-deepseek-ocr)
  fi
  log "Running readiness check"
  "${check_args[@]}"
}

main() {
  install_system_packages
  install_uv
  install_or_upgrade_rust_toolchain
  clone_or_update_repo
  setup_deepseek_env
  local runtime_python
  runtime_python="$(resolve_runtime_python)"
  build_rust_extensions "${runtime_python}"
  run_readiness_check "${runtime_python}"
  log "Bootstrap complete"
}

main "$@"
