PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS branches (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, notes TEXT, version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS athletes (
 id TEXT PRIMARY KEY, legacy_athlete_id TEXT UNIQUE, official_code TEXT UNIQUE, full_name TEXT NOT NULL,
 date_of_birth TEXT, birth_year INTEGER, current_branch_id TEXT REFERENCES branches(id), representative_team TEXT,
 status TEXT NOT NULL DEFAULT 'Chưa xác định', identity_verification_status TEXT NOT NULL DEFAULT 'pending' CHECK(identity_verification_status IN ('pending','verified')),
 notes TEXT, public_profile_allowed INTEGER NOT NULL DEFAULT 0 CHECK(public_profile_allowed IN (0,1)),
 version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tournaments (
 id TEXT PRIMARY KEY, legacy_tournament_id TEXT UNIQUE, tournament_name TEXT NOT NULL, year INTEGER NOT NULL,
 start_date TEXT, end_date TEXT, competition_level TEXT, location TEXT, organizer TEXT, source_url TEXT,
 status TEXT, notes TEXT, version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS achievements (
 id TEXT PRIMARY KEY, legacy_achievement_id TEXT UNIQUE, tournament_id TEXT NOT NULL REFERENCES tournaments(id),
 discipline TEXT, participation_type TEXT, gender_category TEXT, event_name TEXT NOT NULL, age_category TEXT,
 weight_category TEXT, belt_category TEXT, medal_type TEXT CHECK(medal_type IN ('HCV','HCB','HCĐ') OR medal_type IS NULL),
 representative_branch TEXT, team_name TEXT, evidence_url TEXT,
 verification_status TEXT NOT NULL DEFAULT 'pending' CHECK(verification_status IN ('pending','verified','returned')),
 source_row TEXT, source_original_text TEXT, review_notes TEXT, competition_year INTEGER,
 expected_members INTEGER, roster_confirmed INTEGER NOT NULL DEFAULT 0, publication_allowed INTEGER NOT NULL DEFAULT 0,
 source_conflict INTEGER NOT NULL DEFAULT 0, conflict_resolution TEXT, evidence_publication_allowed INTEGER NOT NULL DEFAULT 0,
 verified_by TEXT, verified_at TEXT, created_by TEXT,
 public_search_allowed INTEGER NOT NULL DEFAULT 0 CHECK(public_search_allowed IN (0,1)),
 public_evidence_allowed INTEGER NOT NULL DEFAULT 0 CHECK(public_evidence_allowed IN (0,1)),
 version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS athlete_achievements (
 achievement_id TEXT NOT NULL REFERENCES achievements(id), athlete_id TEXT NOT NULL REFERENCES athletes(id),
 link_status TEXT NOT NULL DEFAULT 'pending', notes TEXT, PRIMARY KEY(achievement_id,athlete_id)
);
CREATE TABLE IF NOT EXISTS verification_queue (
 id TEXT PRIMARY KEY, legacy_verification_id TEXT UNIQUE, tournament_id TEXT REFERENCES tournaments(id),
 original_name TEXT, medal_type TEXT, event_description TEXT, issue_type TEXT, reported_quantity INTEGER,
 source_url TEXT, source_original_text TEXT, source_row TEXT, resolution_status TEXT NOT NULL DEFAULT 'unresolved',
 resolution_notes TEXT, reviewed_by TEXT, reviewed_at TEXT, linked_achievement_id TEXT REFERENCES achievements(id),
 version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','coach','viewer')), can_verify INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_athletes (user_id TEXT REFERENCES users(id),athlete_id TEXT REFERENCES athletes(id),PRIMARY KEY(user_id,athlete_id));
CREATE TABLE IF NOT EXISTS user_branches (user_id TEXT REFERENCES users(id),branch_id TEXT REFERENCES branches(id),PRIMARY KEY(user_id,branch_id));
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_files (
 id TEXT PRIMARY KEY, achievement_id TEXT NOT NULL REFERENCES achievements(id), filename TEXT NOT NULL,
 storage_name TEXT NOT NULL UNIQUE, mime_type TEXT NOT NULL, byte_size INTEGER NOT NULL, sha256 TEXT NOT NULL,
 publication_allowed INTEGER NOT NULL DEFAULT 0, uploaded_by TEXT REFERENCES users(id), created_at TEXT NOT NULL,
 public_access_allowed INTEGER NOT NULL DEFAULT 0 CHECK(public_access_allowed IN (0,1))
);
CREATE TABLE IF NOT EXISTS import_batches (
 id TEXT PRIMARY KEY, file_hash TEXT NOT NULL UNIQUE, filename TEXT, imported_at TEXT, imported_by TEXT,
 summary_json TEXT, workbook_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_records (
 id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL REFERENCES import_batches(id), sheet TEXT NOT NULL,
 excel_row INTEGER NOT NULL, entity_type TEXT, entity_id TEXT, original_json TEXT NOT NULL,
 UNIQUE(batch_id,sheet,excel_row)
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT NOT NULL, entity_type TEXT, entity_id TEXT,
 before_json TEXT, after_json TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_conflicts (
 id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, local_version INTEGER,
 remote_hash TEXT, remote_json TEXT, status TEXT NOT NULL DEFAULT 'unresolved', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ach_tournament ON achievements(tournament_id);
CREATE INDEX IF NOT EXISTS idx_ach_status ON achievements(verification_status,archived);
CREATE INDEX IF NOT EXISTS idx_links_athlete ON athlete_achievements(athlete_id);
CREATE INDEX IF NOT EXISTS idx_athlete_branch ON athletes(current_branch_id);
CREATE INDEX IF NOT EXISTS idx_source_entity ON source_records(entity_type,entity_id);
CREATE INDEX IF NOT EXISTS idx_queue_tournament ON verification_queue(tournament_id);
