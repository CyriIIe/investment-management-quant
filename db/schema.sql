PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bonds (
    secid TEXT PRIMARY KEY,
    isin TEXT,
    nom TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('OFZ-PD', 'OFZ-PK', 'OFZ-IN', 'corporate')),
    date_maturite TEXT,
    taux_coupon REAL
);

CREATE TABLE IF NOT EXISTS collection_runs (
    collection_run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_run_id TEXT NOT NULL,
    secid TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    prix REAL,
    rendement REAL,
    duration INTEGER,
    date_derniere_transaction TEXT,
    volume REAL,
    nb_transactions INTEGER,
    bid REAL,
    ask REAL,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(collection_run_id),
    FOREIGN KEY (secid) REFERENCES bonds(secid)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_secid_timestamp
    ON snapshots (secid, timestamp);

CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_collection_run_secid
    ON snapshots (collection_run_id, secid);

CREATE TABLE IF NOT EXISTS curve_runs (
    curve_run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    univers TEXT NOT NULL,
    methode TEXT NOT NULL,
    parametres TEXT NOT NULL,
    rmse_bp REAL,
    n_bonds INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS curve_residuals (
    curve_run_id TEXT NOT NULL,
    secid TEXT NOT NULL,
    rendement_observe REAL,
    rendement_theorique REAL,
    residu_bp REAL,
    zscore REAL,
    liquidity_score REAL,
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    PRIMARY KEY (curve_run_id, secid),
    FOREIGN KEY (curve_run_id) REFERENCES curve_runs(curve_run_id),
    FOREIGN KEY (secid) REFERENCES bonds(secid)
);

CREATE INDEX IF NOT EXISTS idx_curve_residuals_curve_run_id
    ON curve_residuals (curve_run_id);
