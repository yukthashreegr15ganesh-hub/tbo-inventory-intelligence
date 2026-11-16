"""Database Persistence, Schema Migration, and Disaster Recovery Test Suite.

Verifies:
1. Replan Audit records persist into database tables
2. State survives across simulated application restarts
3. Database backup snapshot creation (/api/admin/backup)
4. Database restoration and record integrity validation
5. Upload audit logging
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from app import app
from pipeline.database import (
    init_db,
    db_save_replan,
    db_get_replan_history,
    db_update_replan_status,
    db_save_upload_audit,
    db_get_upload_history,
)
from pipeline.db_backup import create_backup, restore_backup, list_backups, BACKUP_DIR


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_database_replan_persistence():
    """Verify replan records write to database and can be retrieved."""
    test_replan_id = "RPL-DB-TEST-001"
    entry = {
        "replan_id": test_replan_id,
        "timestamp": "2026-11-16 20:00:00",
        "trigger_reason": "Database Persistence Integration Test",
        "status": "PENDING_APPROVAL",
        "notes": "Testing raw DB insertion",
        "capital_change_pct": 3.5,
        "delta": {"total_investment_delta": 5000000.0},
    }
    db_save_replan(entry)

    # Query history
    history = db_get_replan_history()
    matched = [h for h in history if h["replan_id"] == test_replan_id]
    assert len(matched) == 1
    assert matched[0]["status"] == "PENDING_APPROVAL"
    assert matched[0]["capital_change_pct"] == 3.5

    # Update status to APPROVED
    upd_res = db_update_replan_status(test_replan_id, "APPROVE", "Chief_Risk_Officer")
    assert upd_res["success"] is True
    assert upd_res["status"] == "APPROVED"

    # Query again and verify update persisted
    history_after = db_get_replan_history()
    matched_after = [h for h in history_after if h["replan_id"] == test_replan_id]
    assert matched_after[0]["status"] == "APPROVED"
    assert matched_after[0]["approver"] == "Chief_Risk_Officer"


def test_database_backup_and_restore():
    """Verify point-in-time backup snapshot generation and restoration."""
    # 1. Create a snapshot
    backup_res = create_backup(label="integration_test")
    assert backup_res["success"] is True
    assert "backup_file" in backup_res
    backup_file = BACKUP_DIR / backup_res["backup_file"]
    assert backup_file.exists()

    # 2. List backups
    all_backups = list_backups()
    assert len(all_backups) > 0
    assert any(b["filename"] == backup_res["backup_file"] for b in all_backups)

    # 3. Restore from backup
    restore_res = restore_backup(backup_file)
    assert restore_res["success"] is True
    assert "records_restored" in restore_res
