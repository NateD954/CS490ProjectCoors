from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.auth import getCurrentUserId

client = TestClient(app)


def override_user(user_id: str):
    app.dependency_overrides[getCurrentUserId] = lambda: user_id


def test_s3_006_and_s3_007_persist_and_restore_qa_history_per_target(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    override_user("user_a")
    histories = {"target_1": [], "target_2": []}

    with patch("app.main.supabaseClient") as mock_sb, patch("app.main.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": "Customers praise the espresso."}]}}]},
        )

        def table_router(name):
            tbl = MagicMock()
            if name == "analysis_targets":
                def eq_target(col, val):
                    q = MagicMock()
                    q.execute.return_value.data = [
                        {"id": val, "owner_clerk_id": "user_a", "business_name": f"Cafe {val}", "platform": "GOOGLE_MAPS"}
                    ]
                    return q
                tbl.select.return_value.eq.side_effect = eq_target
            elif name == "reviews":
                tbl.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
                    {"review_text": "Great espresso and fast service."}
                ]
            elif name == "qa_history":
                def do_insert(row):
                    tid = row["analysis_target_id"]
                    record = {"id": f"msg_{len(histories[tid]) + 1}", **row}
                    histories[tid].append(record)
                    res = MagicMock()
                    res.execute.return_value.data = [record]
                    return res

                def eq_hist(col, val):
                    q = MagicMock()
                    q.order.return_value.order.return_value.execute.return_value.data = histories.get(val, [])
                    return q

                tbl.insert.side_effect = do_insert
                tbl.select.return_value.eq.side_effect = eq_hist
            return tbl

        mock_sb.table.side_effect = table_router

        ask_res = client.post("/api/targets/target_1/ask", json={"question": "How is the coffee?"})
        assert ask_res.status_code == 200
        assert len(histories["target_1"]) == 1

        hist_1 = client.get("/api/targets/target_1/history")
        assert hist_1.status_code == 200
        assert len(hist_1.json()) == 1
        assert hist_1.json()[0]["question"] == "How is the coffee?"
        assert hist_1.json()[0]["answer"] == "Customers praise the espresso."

        hist_2 = client.get("/api/targets/target_2/history")
        assert hist_2.status_code == 200
        assert hist_2.json() == []


def test_s3_007_cross_user_cannot_read_history():
    override_user("user_b")

    with patch("app.main.supabaseClient") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "target_1", "owner_clerk_id": "user_a"}
        ]

        res = client.get("/api/targets/target_1/history")
        assert res.status_code == 403


def test_s3_008_clear_history_preserves_target_and_reviews():
    override_user("user_a")
    deleted_tables = []

    with patch("app.main.supabaseClient") as mock_sb:
        def table_router(name):
            tbl = MagicMock()
            if name == "analysis_targets":
                tbl.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "target_1", "owner_clerk_id": "user_a"}
                ]
            elif name == "qa_history":
                tbl.delete.return_value.eq.side_effect = (
                    lambda col, val: deleted_tables.append((name, val)) or MagicMock()
                )
            return tbl

        mock_sb.table.side_effect = table_router

        res = client.delete("/api/targets/target_1/history")
        assert res.status_code == 204
        assert deleted_tables == [("qa_history", "target_1")]


def test_s3_008_cross_user_cannot_clear_history():
    override_user("user_b")

    with patch("app.main.supabaseClient") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "target_1", "owner_clerk_id": "user_a"}
        ]

        res = client.delete("/api/targets/target_1/history")
        assert res.status_code == 403