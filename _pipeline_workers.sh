# Shared pipeline worker defaults (384-core machine, NVMe scratch cache)
# Override via env: REPO_WORKERS, UPLOAD_WORKERS, URL_WORKERS, PREFETCH_SHARDS

_nproc="$(nproc 2>/dev/null || echo 4)"
# Parallel repos: 8 on large machines, floor 2 on small
_default_repo_workers=$(( _nproc / 16 ))
if (( _default_repo_workers < 2 )); then _default_repo_workers=2; fi
if (( _default_repo_workers > 8 )); then _default_repo_workers=8; fi

export REPO_WORKERS="${REPO_WORKERS:-${_default_repo_workers}}"
export UPLOAD_WORKERS="${UPLOAD_WORKERS:-128}"
export URL_WORKERS="${URL_WORKERS:-256}"
export PREFETCH_SHARDS="${PREFETCH_SHARDS:-4}"
export PIPELINE_SCALE_WORKERS="${PIPELINE_SCALE_WORKERS:-1}"
