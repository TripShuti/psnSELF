CREATE TABLE IF NOT EXISTS games (
    np_communication_id TEXT PRIMARY KEY,
    np_title_id TEXT,
    title_name TEXT NOT NULL,
    title_icon_url TEXT,
    platform TEXT,
    defined_bronze INTEGER DEFAULT 0,
    defined_silver INTEGER DEFAULT 0,
    defined_gold INTEGER DEFAULT 0,
    defined_platinum INTEGER DEFAULT 0,
    earned_bronze INTEGER DEFAULT 0,
    earned_silver INTEGER DEFAULT 0,
    earned_gold INTEGER DEFAULT 0,
    earned_platinum INTEGER DEFAULT 0,
    progress INTEGER DEFAULT 0,
    last_updated_datetime TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trophies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    np_communication_id TEXT NOT NULL,
    trophy_id INTEGER NOT NULL,
    trophy_name TEXT,
    trophy_detail TEXT,
    trophy_type TEXT,
    trophy_icon_url TEXT,
    trophy_hidden INTEGER DEFAULT 0,
    trophy_group_id TEXT DEFAULT 'default',
    earned INTEGER DEFAULT 0,
    earned_date_time TEXT,
    trophy_rarity TEXT,
    trophy_earn_rate REAL,
    progress INTEGER,
    progress_rate INTEGER,
    UNIQUE(np_communication_id, trophy_id),
    FOREIGN KEY (np_communication_id) REFERENCES games(np_communication_id)
);

CREATE TABLE IF NOT EXISTS game_stats (
    np_communication_id TEXT PRIMARY KEY,
    title_id TEXT,
    total_seconds INTEGER NOT NULL DEFAULT 0,
    play_count INTEGER DEFAULT 0,
    first_played TEXT,
    last_played TEXT,
    FOREIGN KEY (np_communication_id) REFERENCES games(np_communication_id)
);

CREATE TABLE IF NOT EXISTS play_delta_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    np_communication_id TEXT NOT NULL,
    date TEXT NOT NULL,
    delta_seconds INTEGER NOT NULL,
    UNIQUE(np_communication_id, date),
    FOREIGN KEY (np_communication_id) REFERENCES games(np_communication_id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    trophies_added INTEGER DEFAULT 0,
    games_updated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS friends_cache (
    account_id TEXT PRIMARY KEY,
    online_id TEXT NOT NULL,
    trophy_level INTEGER,
    platinum INTEGER, gold INTEGER, silver INTEGER, bronze INTEGER,
    is_private INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS friend_game_cache (
    account_id TEXT NOT NULL,
    np_communication_id TEXT NOT NULL,
    progress INTEGER, earned_platinum INTEGER, earned_gold INTEGER,
    earned_silver INTEGER, earned_bronze INTEGER,
    is_private INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (account_id, np_communication_id)
);
