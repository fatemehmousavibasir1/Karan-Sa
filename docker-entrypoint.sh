#!/bin/sh
set -e

echo "Waiting for Qdrant at ${QDRANT_URL} ..."
i=0
until python -c "import httpx,os,sys; sys.exit(0 if httpx.get(os.environ['QDRANT_URL'] + '/readyz', timeout=3).status_code == 200 else 1)" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
        echo "Qdrant is not reachable at ${QDRANT_URL}" >&2
        exit 1
    fi
    sleep 2
done

# Builds krs.db only if it does not exist yet (kept in the data volume), then syncs Qdrant.
python ingest_to_qdrant.py

exec "$@"
