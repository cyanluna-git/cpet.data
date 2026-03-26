"""
tests/test_subjects.py — Unit tests for subjects table and related CRUD.

Covers: create_subject, get_subject, list_subjects, update_subject,
link_user_to_subject, unlink_user_from_subject, migration from user_profiles,
and updated submission/dashboard flows with subject_id.
"""

import sqlite3
from pathlib import Path

import pytest

from server.db import (
    _connect,
    create_subject,
    create_submission,
    get_subject,
    get_user,
    init_db,
    link_user_to_subject,
    list_subjects,
    list_submissions_by_user,
    unlink_user_from_subject,
    update_subject,
    upsert_user,
    upsert_user_profile,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path, initialized."""
    path = tmp_path / "test_platform.db"
    init_db(path)
    return path


# ── Schema: subjects table exists ─────────────────────────────────


class TestSubjectsSchema:
    def test_subjects_table_created(self, db_path: Path) -> None:
        """subjects table must be created during init_db."""
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        conn.close()
        names = [t[0] for t in tables]
        assert "subjects" in names

    def test_users_has_subject_id_column(self, db_path: Path) -> None:
        """users table must have a subject_id column after migration."""
        conn = _connect(db_path)
        columns = conn.execute("PRAGMA table_info(users)").fetchall()
        conn.close()
        col_names = [c[1] for c in columns]
        assert "subject_id" in col_names

    def test_submissions_has_subject_id_column(self, db_path: Path) -> None:
        """submissions table must have subject_id and uploaded_by_user_id columns."""
        conn = _connect(db_path)
        columns = conn.execute("PRAGMA table_info(submissions)").fetchall()
        conn.close()
        col_names = [c[1] for c in columns]
        assert "subject_id" in col_names
        assert "uploaded_by_user_id" in col_names


# ── Subject CRUD ──────────────────────────────────────────────────


class TestSubjectCRUD:
    def test_create_subject_returns_dict(self, db_path: Path) -> None:
        """create_subject returns a dict with all fields."""
        subj = create_subject(
            db_path,
            name="홍길동",
            gender="남성",
            birth_year=1990,
        )
        assert isinstance(subj, dict)
        assert subj["name"] == "홍길동"
        assert subj["gender"] == "남성"
        assert subj["birth_year"] == 1990
        assert subj["id"]  # UUID string
        assert len(subj["id"]) == 36

    def test_get_subject_found(self, db_path: Path) -> None:
        """get_subject returns the created subject."""
        created = create_subject(db_path, name="Test", gender="여성", birth_year=1985)
        fetched = get_subject(db_path, created["id"])
        assert fetched is not None
        assert fetched["name"] == "Test"
        assert fetched["gender"] == "여성"

    def test_get_subject_not_found(self, db_path: Path) -> None:
        """get_subject returns None for nonexistent ID."""
        assert get_subject(db_path, "nonexistent-id") is None

    def test_list_subjects_empty(self, db_path: Path) -> None:
        """list_subjects returns empty list when no subjects exist."""
        result = list_subjects(db_path)
        assert result == []

    def test_list_subjects_returns_all(self, db_path: Path) -> None:
        """list_subjects returns all created subjects."""
        create_subject(db_path, name="First")
        create_subject(db_path, name="Second")
        subjects = list_subjects(db_path)
        assert len(subjects) == 2
        names = {s["name"] for s in subjects}
        assert names == {"First", "Second"}

    def test_update_subject(self, db_path: Path) -> None:
        """update_subject modifies specified fields."""
        subj = create_subject(db_path, name="Original", gender="남성")
        updated = update_subject(db_path, subj["id"], name="Updated", gender="여성")
        assert updated is not None
        assert updated["name"] == "Updated"
        assert updated["gender"] == "여성"

    def test_update_subject_unknown_field_raises(self, db_path: Path) -> None:
        """update_subject raises ValueError for unknown field."""
        subj = create_subject(db_path, name="Test")
        with pytest.raises(ValueError, match="Unknown subject field"):
            update_subject(db_path, subj["id"], unknown_field="x")

    def test_update_subject_no_fields_returns_current(self, db_path: Path) -> None:
        """update_subject with no fields returns current state."""
        subj = create_subject(db_path, name="Test")
        result = update_subject(db_path, subj["id"])
        assert result is not None
        assert result["name"] == "Test"

    def test_create_subject_with_body_comp(self, db_path: Path) -> None:
        """create_subject accepts all body-comp fields."""
        subj = create_subject(
            db_path,
            name="Full",
            gender="남성",
            birth_year=1995,
            height_cm=175.5,
            weight_kg=70.0,
            body_fat_pct=15.0,
            skeletal_muscle_mass=30.0,
            bmi=22.7,
            training_level="intermediate",
            notes="Test subject",
        )
        assert subj["height_cm"] == 175.5
        assert subj["weight_kg"] == 70.0
        assert subj["body_fat_pct"] == 15.0
        assert subj["skeletal_muscle_mass"] == 30.0
        assert subj["bmi"] == 22.7
        assert subj["training_level"] == "intermediate"
        assert subj["notes"] == "Test subject"


# ── User-Subject Linking ─────────────────────────────────────────


class TestUserSubjectLink:
    def test_link_user_to_subject(self, db_path: Path) -> None:
        """link_user_to_subject sets user.subject_id."""
        user = upsert_user(db_path, "google-1", "test@test.com", "Test User")
        subj = create_subject(db_path, name="Test Subject", gender="남성", birth_year=1990)
        result = link_user_to_subject(db_path, user["id"], subj["id"])
        assert result is not None
        assert result["subject_id"] == subj["id"]

    def test_unlink_user_from_subject(self, db_path: Path) -> None:
        """unlink_user_from_subject clears user.subject_id."""
        user = upsert_user(db_path, "google-2", "test2@test.com", "Test User 2")
        subj = create_subject(db_path, name="Subject", gender="여성", birth_year=1985)
        link_user_to_subject(db_path, user["id"], subj["id"])
        result = unlink_user_from_subject(db_path, user["id"])
        assert result is not None
        assert result["subject_id"] is None

    def test_get_user_shows_subject_id(self, db_path: Path) -> None:
        """get_user returns the subject_id when linked."""
        user = upsert_user(db_path, "google-3", "test3@test.com", "User3")
        subj = create_subject(db_path, name="Subj3")
        link_user_to_subject(db_path, user["id"], subj["id"])
        fetched = get_user(db_path, user["id"])
        assert fetched is not None
        assert fetched["subject_id"] == subj["id"]


# ── Submission with Subject ──────────────────────────────────────


class TestSubmissionWithSubject:
    def test_create_submission_with_subject_id(self, db_path: Path) -> None:
        """Submissions can store a subject_id."""
        subj = create_subject(db_path, name="피험자A")
        user = upsert_user(db_path, "g-uploader", "up@test.com", "Uploader")
        sid = create_submission(
            db_path,
            description="test with subject",
            file_manifest=[],
            workspace_path="/ws",
            subject_id=subj["id"],
            uploaded_by_user_id=user["id"],
        )
        from server.db import get_submission
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["subject_id"] == subj["id"]
        assert sub["uploaded_by_user_id"] == user["id"]

    def test_list_submissions_by_user_via_subject(self, db_path: Path) -> None:
        """list_submissions_by_user finds submissions linked by subject_id."""
        subj = create_subject(db_path, name="피험자B")
        user = upsert_user(db_path, "g-user-b", "b@test.com", "UserB")
        link_user_to_subject(db_path, user["id"], subj["id"])

        # Create a submission linked to subject but not directly to user
        sid = create_submission(
            db_path,
            description="linked via subject",
            file_manifest=[],
            workspace_path="/ws",
            subject_id=subj["id"],
        )

        # list_submissions_by_user should find it via user.subject_id
        subs = list_submissions_by_user(db_path, user["id"])
        assert len(subs) == 1
        assert subs[0]["id"] == sid


# ── Migration from user_profiles ─────────────────────────────────


class TestProfileToSubjectMigration:
    def test_migration_creates_subject_from_profile(self, tmp_path: Path) -> None:
        """Users with profiles but no subject_id get a subject on init_db."""
        db_path = tmp_path / "migration_test.db"
        init_db(db_path)

        # Create a user and profile without subject_id
        user = upsert_user(db_path, "g-migrate", "migrate@test.com", "Migrator")
        upsert_user_profile(db_path, user["id"], gender="남성", birth_year=1992)

        # Clear the subject_id that might have been set
        conn = _connect(db_path)
        conn.execute("UPDATE users SET subject_id = NULL WHERE id = ?", (user["id"],))
        conn.commit()
        conn.close()

        # Re-run init_db to trigger migration
        init_db(db_path)

        # Verify a subject was created and linked
        updated_user = get_user(db_path, user["id"])
        assert updated_user is not None
        assert updated_user["subject_id"] is not None

        subj = get_subject(db_path, updated_user["subject_id"])
        assert subj is not None
        assert subj["name"] == "Migrator"
        assert subj["gender"] == "남성"
        assert subj["birth_year"] == 1992

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        """Running init_db multiple times does not create duplicate subjects."""
        db_path = tmp_path / "idempotent_test.db"
        init_db(db_path)

        user = upsert_user(db_path, "g-idem", "idem@test.com", "Idem")
        upsert_user_profile(db_path, user["id"], gender="여성", birth_year=1988)

        conn = _connect(db_path)
        conn.execute("UPDATE users SET subject_id = NULL WHERE id = ?", (user["id"],))
        conn.commit()
        conn.close()

        init_db(db_path)
        init_db(db_path)  # second run

        subjects = list_subjects(db_path)
        # Should have exactly one subject (not duplicated)
        subject_names = [s["name"] for s in subjects if s["name"] == "Idem"]
        assert len(subject_names) == 1


# ── Profile syncs to Subject ─────────────────────────────────────


class TestProfileSubjectSync:
    def test_profile_update_syncs_to_subject(self, db_path: Path) -> None:
        """Updating profile fields that overlap with subject syncs them."""
        user = upsert_user(db_path, "g-sync", "sync@test.com", "Syncer")
        subj = create_subject(db_path, name="Syncer", gender="남성")
        link_user_to_subject(db_path, user["id"], subj["id"])

        # Update profile with overlapping fields
        upsert_user_profile(
            db_path, user["id"],
            weight_kg=72.5,
            height_cm=178.0,
            gender="여성",
        )

        # Verify subject was updated
        updated_subj = get_subject(db_path, subj["id"])
        assert updated_subj is not None
        assert updated_subj["weight_kg"] == 72.5
        assert updated_subj["height_cm"] == 178.0
        assert updated_subj["gender"] == "여성"
