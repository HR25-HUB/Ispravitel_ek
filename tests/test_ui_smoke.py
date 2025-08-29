def test_ui_import_smoke(monkeypatch):
    # Ensure mock mode to avoid NotImplemented real clients
    monkeypatch.setenv("USE_MOCKS", "1")
    # Import should not raise
    import ui_streamlit  # noqa: F401
    assert True
