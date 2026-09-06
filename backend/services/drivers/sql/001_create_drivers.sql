-- Run once against the formula1 database as its administrator.
BEGIN;
CREATE TABLE IF NOT EXISTS public.drivers (
    drivers_current_position INTEGER NOT NULL,
    drivers_current_position_str TEXT NOT NULL,
    drivers_current_total_points NUMERIC NOT NULL,
    drivers_current_total_wins INTEGER NOT NULL,
    drivers_id TEXT PRIMARY KEY,
    drivers_number INTEGER NOT NULL,
    drivers_driver_code TEXT NOT NULL,
    drivers_driver_url TEXT NOT NULL,
    drivers_first_name TEXT NOT NULL,
    drivers_last_name TEXT NOT NULL,
    drivers_birthday DATE NOT NULL,
    drivers_nationality TEXT NOT NULL,
    drivers_current_team_ids TEXT[] NOT NULL,
    drivers_current_team_urls TEXT[] NOT NULL,
    drivers_current_team_names TEXT[] NOT NULL,
    drivers_current_team_nationalities TEXT[] NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMIT;
