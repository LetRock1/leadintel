"""Two people on the team acting on the same thing at the same moment: the first one's work stands, the second is
told, and nothing is written twice (a note, an audit line)."""

from __future__ import annotations

import pytest

from app.core.errors import Conflict


def test_two_people_closing_the_same_task_at_once(client, owner, new_learner, monkeypatch):
    from app import db
    from app.services import tasks

    learner = new_learner("Race Task")
    uid = learner["user"]["id"]
    task_id = db.execute(
        """INSERT INTO sales_tasks (user_id, task_type, title, detail, expected_gain)
           VALUES (?, 'call', 'Call', '', 100)""",
        (uid,),
    )
    me = {"id": owner["member"]["id"], "name": "Owner", "role": "admin"}
    seen = tasks.open_task(task_id, me)
    # both people loaded the open task before either saved: the second save must not go through
    monkeypatch.setattr(tasks, "open_task", lambda *_a, **_k: dict(seen))
    notes_before = db.fetchone("SELECT COUNT(*) AS c FROM lead_notes WHERE user_id=?", (uid,))["c"]
    assert tasks.complete(task_id, me, "reached", "Spoke to them first.")["message"] == "Saved."
    with pytest.raises(Conflict):
        tasks.complete(task_id, me, "no_answer", "A second, late outcome.")
    row = db.fetchone("SELECT status, outcome FROM sales_tasks WHERE id=?", (task_id,))
    assert (row["status"], row["outcome"]) == ("done", "reached")
    notes = db.fetchone("SELECT COUNT(*) AS c FROM lead_notes WHERE user_id=?", (uid,))["c"]
    assert notes == notes_before + 1  # the late outcome left no note


def test_two_people_marking_the_same_call_back_done(client, owner, new_learner):
    from support import API, CRM

    learner = new_learner("Race Callback")
    r = client.post(f"{API}/callback", json={"phone": "+91 98765 43210"}, headers=learner["headers"])
    assert r.status_code == 200, r.text
    cid = r.json()["callback_id"]
    first = client.post(f"{CRM}/callbacks/{cid}/done", json={"note": "Called."}, headers=owner["headers"])
    second = client.post(f"{CRM}/callbacks/{cid}/done", json={"note": "Called too."}, headers=owner["headers"])
    assert first.status_code == 200 and second.status_code == 409
