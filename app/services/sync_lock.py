import threading

# One process-wide lock shared by UI and API full-sync entry points.
# This prevents /sync/run and /sync/all from running a full synchronization
# concurrently inside the same application process.
SYNC_LOCK = threading.Lock()
