from pathlib import Path

PLUGIN_ROOT = Path(__file__).parents[1]


def test_manage_mutation_routes_accept_frontend_post_requests():
    frontend = (PLUGIN_ROOT / "pages/manage/app.js").read_text()
    backend = (PLUGIN_ROOT / "main.py").read_text()

    # AstrBotPluginPage.apiPost() is the bridge used by the current management UI.
    assert "await post(`images/${id}/tags`" in frontend
    route = '(f"/{PLUGIN_NAME}/images/<image_id>/tags", self.api_image_tags,'
    start = backend.index(route)
    registration = backend[start:backend.index("\n", start)]
    assert '["PUT", "POST"]' in registration


def test_all_management_mutations_have_post_handlers():
    frontend = (PLUGIN_ROOT / "pages/manage/app.js").read_text()
    backend = (PLUGIN_ROOT / "main.py").read_text()
    expected = {
        "tags/${id}/rename": 'tags/<tag_id>/rename',
        "tags/${e.currentTarget.dataset.delete}/delete": 'tags/<tag_id>/delete',
        "images/${id}/tags": 'images/<image_id>/tags',
        "images/${b.dataset.enabled}/enabled": 'images/<image_id>/enabled',
        "images/${e.currentTarget.dataset.imgDelete}/delete": 'images/<image_id>/delete',
        "images/batch/enabled": 'images/batch/enabled',
        "images/batch/delete": 'images/batch/delete',
        "tags": 'tags',
        "upload/commit": 'upload/commit',
    }
    for frontend_endpoint, backend_endpoint in expected.items():
        assert frontend_endpoint in frontend
        marker = f'(f"/{{PLUGIN_NAME}}/{backend_endpoint}"'
        assert marker in backend
        registrations = []
        offset = 0
        while True:
            try:
                start = backend.index(marker, offset)
            except ValueError:
                break
            registrations.append(backend[start:backend.index("\n", start)])
            offset = start + len(marker)
        assert any('["POST"]' in row or '["PUT", "POST"]' in row for row in registrations), frontend_endpoint
