# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
- CI pipeline (Ruff + Pytest) and status badge in README.
- Retry metrics in report (counts per step) and extended observability.

## [2025-08-28]
### Added
- Configurable retries and timeouts for real CatalogAPI client.
- Exponential backoff with optional jitter in CatalogAPI and internal pipeline retries.
- New environment variables:
  - Catalog API: `CATALOG_TIMEOUT_SEC`, `CATALOG_RETRIES`, `CATALOG_BACKOFF_BASE_MS`, `CATALOG_BACKOFF_MAX_MS`, `CATALOG_BACKOFF_JITTER_MS`.
  - Pipeline: `BACKOFF_BASE_MS`, `BACKOFF_MAX_MS`, `BACKOFF_JITTER_MS`.
- Dependency Injection wiring for new configuration in `services.py`.
- Tests covering retry and backoff behavior:
  - `test_catalog_api_real.py` (timeouts → success, non-200, exhausted retries, sleep backoff).
  - `test_services.py` (DI wiring of backoff params).
  - `test_config.py` (defaults and env parsing for new fields).

### Changed
- `reporter.save_report()` now falls back to `openpyxl` if `xlsxwriter` is unavailable.
- Documentation (`README.md`) updated with new configuration and behavior.
- Minor lint improvements and test cleanups.

### Status
- All tests passing locally (`pytest -q`).
