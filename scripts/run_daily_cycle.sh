#!/usr/bin/env bash
# Exécute un cycle de collecte puis, seulement si les entrées de courbe ont changé,
# le moteur de courbe. Ce fichier est appelé par le service systemd quotidien.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
DATABASE_PATH="$PROJECT_DIR/data/moex.sqlite3"
LOG_DIR="$PROJECT_DIR/logs"
MOSCOW_DATE="$(TZ=Europe/Moscow date +%F)"
LOG_FILE="$LOG_DIR/$MOSCOW_DATE.log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

echo "===== cycle démarré $(TZ=Europe/Moscow date --iso-8601=seconds) MSK ====="

latest_completed_run() {
    "$PYTHON" - "$DATABASE_PATH" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    row = connection.execute(
        """
        SELECT collection_run_id
        FROM collection_runs
        WHERE status = 'completed'
        ORDER BY completed_at DESC
        LIMIT 1
        """
    ).fetchone()
print(row[0] if row else "")
PY
}

previous_run_id="$(latest_completed_run)"
"$PYTHON" "$PROJECT_DIR/collector.py"
current_run_id="$(latest_completed_run)"

if [[ -z "$current_run_id" || "$current_run_id" == "$previous_run_id" ]]; then
    echo "ERREUR: la collecte a réussi sans cycle complet identifiable."
    exit 1
fi

if [[ -n "$previous_run_id" ]]; then
    changed_inputs="$($PYTHON - "$DATABASE_PATH" "$current_run_id" "$previous_run_id" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM snapshots AS current
        LEFT JOIN snapshots AS previous
          ON previous.collection_run_id = ? AND previous.secid = current.secid
        WHERE current.collection_run_id = ?
          AND (
              previous.secid IS NULL
              OR current.prix IS NOT previous.prix
              OR current.rendement IS NOT previous.rendement
              OR current.duration IS NOT previous.duration
          )
        """,
        (sys.argv[3], sys.argv[2]),
    ).fetchone()[0]
print(count)
PY
)"
    if [[ "$changed_inputs" == "0" ]]; then
        echo "Collecte terminée, mais entrées de courbe inchangées: moteur non exécuté."
        echo "===== cycle terminé $(TZ=Europe/Moscow date --iso-8601=seconds) MSK ====="
        exit 0
    fi
fi

"$PYTHON" "$PROJECT_DIR/curve_engine.py"
echo "===== cycle terminé $(TZ=Europe/Moscow date --iso-8601=seconds) MSK ====="
