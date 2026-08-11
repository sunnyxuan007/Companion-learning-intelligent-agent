from __future__ import annotations

import json
import time
from typing import Any

from deeptutor.services.custom.db import get_connection
from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS


def get_user_weights(user_id: str) -> dict[str, float]:
    conn = get_connection()
    row = conn.execute(
        "SELECT settings_json FROM user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()

    if row is None:
        return dict(VOLUNTEER_DEFAULT_WEIGHTS)

    settings = json.loads(row["settings_json"])
    weights = settings.get("volunteer_weights")
    if weights is None:
        return dict(VOLUNTEER_DEFAULT_WEIGHTS)
    return weights


def set_user_weights(user_id: str, weights: dict[str, float]) -> None:
    now = time.time()
    conn = get_connection()
    row = conn.execute(
        "SELECT settings_json FROM user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    settings = json.loads(row["settings_json"]) if row else {}
    settings["volunteer_weights"] = weights
    conn.execute(
        """INSERT INTO user_settings (user_id, settings_json, created_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               settings_json = excluded.settings_json,
               updated_at = excluded.updated_at""",
        (user_id, json.dumps(settings, ensure_ascii=False), now, now),
    )
    conn.commit()
    conn.close()


def reset_user_weights(user_id: str) -> dict[str, float]:
    defaults = dict(VOLUNTEER_DEFAULT_WEIGHTS)
    set_user_weights(user_id, defaults)
    return defaults
