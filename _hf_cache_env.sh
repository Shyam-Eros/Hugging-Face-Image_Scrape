# NVMe scratch cache (HF downloads) — safe to delete when no pipeline is running
LOCAL_HF_CACHE="/mnt/ai-dev-team-1-disk/shyam/scratch/hf-cache"
export HF_HOME="${HF_HOME:-${LOCAL_HF_CACHE}/hub}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${LOCAL_HF_CACHE}/datasets}"
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
mkdir -p "${LOCAL_HF_CACHE}/datasets" "${LOCAL_HF_CACHE}/hub"
echo "active $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${LOCAL_HF_CACHE}/CACHE_ROOT"
# Progress/scheduler on /workspace (small JSON state files)
mkdir -p /workspace/shyam/hf-cache/progress /workspace/shyam/hf-cache/profiles /workspace/shyam/hf-cache/scheduler
