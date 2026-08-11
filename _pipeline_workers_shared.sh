# Polite defaults for shared VM (384-core box used by many developers)
export REPO_WORKERS="${REPO_WORKERS:-1}"
export UPLOAD_WORKERS="${UPLOAD_WORKERS:-48}"
export URL_WORKERS="${URL_WORKERS:-48}"
export PREFETCH_SHARDS="${PREFETCH_SHARDS:-2}"
export PIPELINE_SCALE_WORKERS="${PIPELINE_SCALE_WORKERS:-0}"
