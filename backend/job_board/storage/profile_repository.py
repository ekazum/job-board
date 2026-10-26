"""Data access for the single-row profile table; the statements live in sql/profile/."""

import json
import sqlite3

from job_board.models.profile import Profile
from job_board.models.profile_patch import ProfilePatch
from job_board.storage.database import Database
from job_board.utils.sql_files import sql


class ProfileRepository:
    """Reads and writes the candidate profile (at most one row)."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self) -> Profile | None:
        """The profile; None only when its row is missing (the schema creates it, with no CV and no location)."""
        with self._database.transaction() as connection:
            row = connection.execute(sql("profile/get.sql")).fetchone()
        return None if row is None else self._to_profile(row)

    def save_upload(self, cv_text: str, filename: str) -> Profile:
        """Store an uploaded CV's extracted text and file name; targets and the location written earlier are kept."""
        with self._database.transaction() as connection:
            connection.execute(sql("profile/save_upload.sql"), {"cv_text": cv_text, "filename": filename})
        return self._existing()

    def update(self, patch: ProfilePatch) -> Profile:
        """Apply the fields the patch sets (the others keep their stored value); creates the profile when there is
        none."""
        values = {
            "cv_text": patch.cv_text,
            "targets": patch.targets,
            "location": patch.location,
            "allow_fully_remote": None if patch.allow_fully_remote is None else int(patch.allow_fully_remote),
            "include_keywords": None if patch.include_keywords is None else json.dumps(patch.include_keywords),
            "exclude_keywords": None if patch.exclude_keywords is None else json.dumps(patch.exclude_keywords),
        }
        with self._database.transaction() as connection:
            connection.execute(sql("profile/create.sql"))
            connection.execute(sql("profile/update.sql"), values)
        return self._existing()

    def _existing(self) -> Profile:
        """The profile right after a write."""
        profile = self.get()
        if profile is None:
            raise RuntimeError("profile row missing right after it was written")
        return profile

    @staticmethod
    def _to_profile(row: sqlite3.Row) -> Profile:
        """Convert the profile row into the API model; allow_fully_remote is stored as 0/1, the keywords as JSON
        arrays."""
        data = dict(row)
        data["allow_fully_remote"] = bool(data["allow_fully_remote"])
        data["include_keywords"] = json.loads(data["include_keywords"])
        data["exclude_keywords"] = json.loads(data["exclude_keywords"])
        return Profile.model_validate(data)
