"""
One-shot script:
  – adds category_search / record_type_search text mirrors
  – keeps them in sync via triggers
  – builds BM25 indexes on the mirrors
  – safe to run repeatedly (idempotent)
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

# ------------------------------------------------------
# 1.  Env / connection
# ------------------------------------------------------
load_dotenv()
CONN_STR = os.getenv("DATABASE_URL")
if not CONN_STR:
    sys.exit("❌  DATABASE_URL not set in environment")

# ------------------------------------------------------
# 2.  SQL helpers
# ------------------------------------------------------

# need to add text based columns for the enum as bm25 only works for text based
ADD_COLS = """
ALTER TABLE long_term_memory
    ADD COLUMN IF NOT EXISTS category_search text;

ALTER TABLE healthcare_records
    ADD COLUMN IF NOT EXISTS record_type_search text;
"""

# backfill for those without text columns for the enum columns
BACKFILL = """
UPDATE long_term_memory
SET    category_search = category::text
WHERE  category_search IS NULL;

UPDATE healthcare_records
SET    record_type_search = record_type::text
WHERE  record_type_search IS NULL;
"""

# custom triggers to add to the text columns upon insertion into the enum columns
CREATE_TRIGGERS = """
-- trigger function for long_term_memory
CREATE OR REPLACE FUNCTION trg_ltm_search_mirror()
RETURNS TRIGGER LANGUAGE plpgsql AS
$$
BEGIN
    NEW.category_search := NEW.category::text;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ltm_search_mirror ON long_term_memory;
CREATE TRIGGER trg_ltm_search_mirror
BEFORE INSERT OR UPDATE OF category ON long_term_memory
FOR EACH ROW EXECUTE FUNCTION trg_ltm_search_mirror();

-- trigger function for healthcare_records
CREATE OR REPLACE FUNCTION trg_hr_search_mirror()
RETURNS TRIGGER LANGUAGE plpgsql AS
$$
BEGIN
    NEW.record_type_search := NEW.record_type::text;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_hr_search_mirror ON healthcare_records;
CREATE TRIGGER trg_hr_search_mirror
BEFORE INSERT OR UPDATE OF record_type ON healthcare_records
FOR EACH ROW EXECUTE FUNCTION trg_hr_search_mirror();
"""

# creating the bm25 indexes for each table
 # elederly_id is part of the index but will influence the score evenly, only use exact match
 # the rest uses lowercase, remove stop words, and uses stemming and fuzzy match
BM25_INDEXES = """
DROP INDEX IF EXISTS idx_stm_bm25;
DROP INDEX IF EXISTS idx_ltm_bm25;
DROP INDEX IF EXISTS idx_health_bm25;

CREATE INDEX idx_stm_bm25
ON short_term_memory
USING bm25 (id, content, elderly_id)
WITH (
    key_field = 'id',
    text_fields = '{
        "content": {
            "tokenizer": {"type": "en_stem"},
            "token_filters": [
                {"type": "lowercase"},
                {"type": "stop_words"},
                {"type": "stemmer", "language": "english"},
                {"type": "fuzzy", "max_distance": 2}
            ]
        }
    }'
);

CREATE INDEX idx_ltm_bm25
ON long_term_memory
USING bm25 (id, category_search, key, value, elderly_id)
WITH (
    key_field = 'id',
    text_fields = '{
        "category_search": {
            "tokenizer": {"type": "en_stem"},
            "token_filters": [
                {"type": "lowercase"},
                {"type": "stop_words"},
                {"type": "stemmer", "language": "english"},
                {"type": "fuzzy", "max_distance": 2}
            ]
        },
        "key": {
            "tokenizer": {"type": "en_stem"},
            "token_filters": [
                {"type": "lowercase"},
                {"type": "stop_words"},
                {"type": "stemmer", "language": "english"},
                {"type": "fuzzy", "max_distance": 2}
            ]
        },
        "value": {
            "tokenizer": {"type": "en_stem"},
            "token_filters": [
                {"type": "lowercase"},
                {"type": "stop_words"},
                {"type": "stemmer", "language": "english"},
                {"type": "fuzzy", "max_distance": 2}
            ]
        }
    }'
);

CREATE INDEX idx_health_bm25
ON healthcare_records
USING bm25 (id, record_type_search, description, elderly_id)
WITH (
    key_field = 'id',
    text_fields = '{
        "record_type_search": {
            "tokenizer": {"type": "en_stem"},
            "token_filters": [
                {"type": "lowercase"},
                {"type": "stop_words"},
                {"type": "stemmer", "language": "english"},
                {"type": "fuzzy", "max_distance": 2}
            ]
        },
        "description": {
            "tokenizer": {"type": "en_stem"},
            "token_filters": [
                {"type": "lowercase"},
                {"type": "stop_words"},
                {"type": "stemmer", "language": "english"},
                {"type": "fuzzy", "max_distance": 2}
            ]
        }
    }'
);
"""

# ------------------------------------------------------
# 3.  run everything in one transaction
# ------------------------------------------------------
def main():
    try:
        with psycopg2.connect(CONN_STR) as conn:
            with conn.cursor() as cur:
                print("🔧  Adding text-search mirrors …")
                cur.execute(ADD_COLS)

                print("🔧  Back-filling existing rows …")
                cur.execute(BACKFILL)

                print("🔧  Installing triggers …")
                cur.execute(CREATE_TRIGGERS)

                print("🔧  Creating BM25 indexes …")
                cur.execute(BM25_INDEXES)

                print("✅  All done – mirrors + triggers + BM25 indexes ready!")
    except Exception as e:
        print(f"❌  Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()