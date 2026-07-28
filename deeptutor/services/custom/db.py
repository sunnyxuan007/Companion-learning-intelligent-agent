from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path


def get_custom_db_path() -> Path:
    from deeptutor.services.path_service import get_path_service
    ps = get_path_service()
    return ps.user_data_dir / "custom" / "deeptutor_custom.db"


def get_connection() -> sqlite3.Connection:
    db_path = get_custom_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS colleges (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        province TEXT NOT NULL,
        city TEXT NOT NULL,
        type TEXT,
        level TEXT,
        is_public INTEGER DEFAULT 1,
        tags TEXT DEFAULT '[]',
        dorm_score REAL DEFAULT 0,
        city_vitality REAL DEFAULT 0,
        cost_index REAL DEFAULT 0,
        employment_rate REAL DEFAULT 0,
        avg_salary REAL DEFAULT 0,
        scholarship_score REAL DEFAULT 0,
        campus_area REAL DEFAULT 0,
        library_volume REAL DEFAULT 0,
        graduate_rate REAL DEFAULT 0,
        masters_count INTEGER DEFAULT 0,
        double_first_class_disciplines TEXT DEFAULT '[]',
        ruanke_ranking INTEGER DEFAULT 0,
        xiaoyouhui_ranking INTEGER DEFAULT 0,
        admission_charter_url TEXT DEFAULT '',
        transfer_policy TEXT DEFAULT '',
        scholarship_info TEXT DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS majors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT,
        subject_group TEXT,
        description TEXT,
        career_paths TEXT DEFAULT '[]',
        course_intro TEXT DEFAULT '',
        graduate_directions TEXT DEFAULT '[]',
        salary_range TEXT DEFAULT '',
        discipline_evaluation TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS college_majors (
        college_id TEXT NOT NULL REFERENCES colleges(id),
        major_id TEXT NOT NULL REFERENCES majors(id),
        batch TEXT,
        years INTEGER DEFAULT 4,
        degree TEXT DEFAULT '学士',
        tuition REAL DEFAULT 0,
        min_rank_2024 INTEGER DEFAULT 0,
        min_rank_2023 INTEGER DEFAULT 0,
        min_rank_2022 INTEGER DEFAULT 0,
        PRIMARY KEY (college_id, major_id)
    );
    CREATE TABLE IF NOT EXISTS study_records (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        record_type TEXT NOT NULL,
        subject TEXT NOT NULL,
        title TEXT,
        content_json TEXT DEFAULT '{}',
        score REAL,
        total REAL,
        weak_points TEXT DEFAULT '[]',
        strong_points TEXT DEFAULT '[]',
        created_at REAL NOT NULL,
        exam_date TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_study_records_user ON study_records(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_study_records_subject ON study_records(user_id, subject);
    CREATE INDEX IF NOT EXISTS idx_college_majors_college ON college_majors(college_id);
    CREATE INDEX IF NOT EXISTS idx_college_majors_major ON college_majors(major_id);

    CREATE TABLE IF NOT EXISTS advisor_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school TEXT NOT NULL,
        college TEXT,
        name TEXT NOT NULL,
        score REAL DEFAULT 0,
        review_text TEXT,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_advisor_school ON advisor_evaluations(school);
    CREATE INDEX IF NOT EXISTS idx_advisor_name ON advisor_evaluations(name);

    CREATE TABLE IF NOT EXISTS user_settings (
        user_id TEXT PRIMARY KEY,
        settings_json TEXT NOT NULL DEFAULT '{}',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admission_ranks (
        college_id TEXT NOT NULL REFERENCES colleges(id),
        major_id TEXT NOT NULL,
        province TEXT NOT NULL,
        year INTEGER NOT NULL,
        batch TEXT,
        min_rank INTEGER DEFAULT 0,
        min_score REAL DEFAULT 0,
        enrollment_count INTEGER DEFAULT 0,
        exam_category TEXT DEFAULT '',
        group_code TEXT DEFAULT '',
        PRIMARY KEY (college_id, major_id, province, year, exam_category, group_code)
    );
    CREATE INDEX IF NOT EXISTS idx_admission_ranks_college ON admission_ranks(college_id);
    CREATE INDEX IF NOT EXISTS idx_admission_ranks_province ON admission_ranks(province);

    CREATE TABLE IF NOT EXISTS score_rank_segments (
        province TEXT NOT NULL,
        year INTEGER NOT NULL,
        exam_category TEXT NOT NULL,
        score INTEGER NOT NULL,
        cumulative_rank INTEGER NOT NULL,
        batch_category TEXT DEFAULT '本科',
        PRIMARY KEY (province, year, exam_category, score, batch_category)
    );

    CREATE TABLE IF NOT EXISTS import_batch (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        province TEXT,
        year INTEGER,
        exam_category TEXT DEFAULT '',
        total_rows INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        error_count INTEGER DEFAULT 0,
        created_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS import_error (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER REFERENCES import_batch(id),
        row_number INTEGER,
        reason TEXT,
        raw_data TEXT,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_import_batch_source ON import_batch(source);

    CREATE TABLE IF NOT EXISTS volunteer_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        province TEXT NOT NULL,
        exam_category TEXT NOT NULL,
        rank INTEGER NOT NULL,
        province_rules TEXT NOT NULL,
        slots TEXT NOT NULL,
        status TEXT DEFAULT 'draft',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_volunteer_plans_user ON volunteer_plans(user_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS medical_restrictions (
        code TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        severity TEXT DEFAULT 'medium'
    );
    CREATE TABLE IF NOT EXISTS major_medical_restrictions (
        major_id TEXT NOT NULL,
        restriction_code TEXT NOT NULL REFERENCES medical_restrictions(code),
        PRIMARY KEY (major_id, restriction_code)
    );
    CREATE TABLE IF NOT EXISTS user_favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        item_type TEXT NOT NULL,
        item_id TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_favorites_user ON user_favorites(user_id, item_type, item_id);
    CREATE TABLE IF NOT EXISTS browsing_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        item_type TEXT NOT NULL,
        item_id TEXT NOT NULL,
        viewed_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_browsing_user ON browsing_history(user_id, viewed_at DESC);
    """
    conn = get_connection()
    conn.executescript(sql)
    # Migration: add college extended fields
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(colleges)").fetchall()]
        for col in ("graduate_rate", "masters_count", "double_first_class_disciplines", "ruanke_ranking", "xiaoyouhui_ranking"):
            if col not in cols:
                conn.execute(f"ALTER TABLE colleges ADD COLUMN {col} REAL DEFAULT 0")
    except Exception:
        pass
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(colleges)").fetchall()]
        for col in ("admission_charter_url", "transfer_policy", "scholarship_info"):
            if col not in cols:
                conn.execute(f"ALTER TABLE colleges ADD COLUMN {col} TEXT DEFAULT ''")
    except Exception:
        pass
    # Migration: add major extended fields
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(majors)").fetchall()]
        for col in ("course_intro", "salary_range", "discipline_evaluation"):
            if col not in cols:
                conn.execute(f"ALTER TABLE majors ADD COLUMN {col} TEXT DEFAULT ''")
        if "graduate_directions" not in cols:
            conn.execute("ALTER TABLE majors ADD COLUMN graduate_directions TEXT DEFAULT '[]'")
    except Exception:
        pass
    # Migration: add exam_category to existing admission_ranks if missing
    try:
        conn.execute("ALTER TABLE admission_ranks ADD COLUMN exam_category TEXT DEFAULT ''")
    except Exception:
        pass
    # Recreate index if needed (old primary key didn't have exam_category)
    try:
        conn.execute("DROP INDEX IF EXISTS idx_admission_ranks_unique")
    except Exception:
        pass
    # Migration: add group_code column and rebuild PK for 专业组 support
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(admission_ranks)").fetchall()]
        if "group_code" not in cols:
            conn.execute("ALTER TABLE admission_ranks RENAME TO admission_ranks_old")
            conn.executescript("""
                CREATE TABLE admission_ranks (
                    college_id TEXT NOT NULL REFERENCES colleges(id),
                    major_id TEXT NOT NULL,
                    province TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    batch TEXT,
                    min_rank INTEGER DEFAULT 0,
                    min_score REAL DEFAULT 0,
                    enrollment_count INTEGER DEFAULT 0,
                    exam_category TEXT DEFAULT '',
                    group_code TEXT DEFAULT '',
                    PRIMARY KEY (college_id, major_id, province, year, exam_category, group_code)
                );
                INSERT INTO admission_ranks
                    (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code)
                    SELECT college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, ''
                    FROM admission_ranks_old;
                CREATE INDEX idx_admission_ranks_college ON admission_ranks(college_id);
                CREATE INDEX idx_admission_ranks_province ON admission_ranks(province);
                DROP TABLE admission_ranks_old;
            """)
    except Exception:
        pass  # table might not exist yet; CREATE TABLE handles it
    # Migration: add subject_requirement / metadata / timestamps to college_majors
    for col, coltype in [
        ("subject_requirement", "TEXT DEFAULT ''"),
        ("metadata", "TEXT DEFAULT '{}'"),
        ("created_at", "REAL DEFAULT 0"),
        ("updated_at", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE college_majors ADD COLUMN {col} {coltype}")
        except Exception:
            pass
    # Migration: add extra columns to majors
    for col, coltype in [
        ("ruanke_ranking", "INTEGER DEFAULT 0"),
        ("discipline_evaluation", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE majors ADD COLUMN {col} {coltype}")
        except Exception:
            pass
    # Migration: add city_tier and region to colleges
    for col, coltype in [
        ("city_tier", "TEXT DEFAULT ''"),
        ("region", "TEXT DEFAULT ''"),
    ]:
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(colleges)").fetchall()]
            if col not in cols:
                conn.execute(f"ALTER TABLE colleges ADD COLUMN {col} {coltype}")
        except Exception:
            pass
    conn.commit()
    conn.close()
    from deeptutor.services.custom.medical_dao import seed_default_restrictions
    seed_default_restrictions()
