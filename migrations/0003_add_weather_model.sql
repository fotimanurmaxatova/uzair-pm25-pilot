-- 0003: record which weather model produced each row (decision 0003).
-- Rows stored before this migration were requested without an explicit model;
-- Open-Meteo's default is best_match, so they receive that value.
ALTER TABLE observations ADD COLUMN weather_model TEXT NOT NULL DEFAULT 'best_match';
