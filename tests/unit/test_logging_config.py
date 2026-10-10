"""Unit tests for cna.core.logging_config."""

from __future__ import annotations

import json
import logging

from cna.core.logging_config import (
    EngagementFilter,
    JSONFormatter,
    get_logger,
    setup_logging,
)

# ── JSONFormatter ──────────────────────────────────────────────────────────────


class TestJSONFormatter:
    def _make_record(self, msg: str = "hello", level=logging.INFO, **extra) -> logging.LogRecord:
        record = logging.LogRecord(
            name="cna.test",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_basic_output_is_valid_json(self):
        fmt = JSONFormatter()
        record = self._make_record("test message")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["message"] == "test message"
        assert data["level"] == "INFO"
        assert data["logger"] == "cna.test"

    def test_engagement_id_present_when_set(self):
        fmt = JSONFormatter()
        record = self._make_record("msg", engagement_id="eng-001")
        data = json.loads(fmt.format(record))
        assert data["engagement_id"] == "eng-001"

    def test_engagement_id_none_when_not_set(self):
        fmt = JSONFormatter()
        record = self._make_record("msg")
        data = json.loads(fmt.format(record))
        assert data["engagement_id"] is None

    def test_extra_fields_merged_into_output(self):
        fmt = JSONFormatter()
        record = self._make_record("msg", account_id="123456789012")
        data = json.loads(fmt.format(record))
        assert data["account_id"] == "123456789012"

    def test_exception_info_formatted(self):
        fmt = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = self._make_record("with exception")
        record.exc_info = exc_info
        data = json.loads(fmt.format(record))
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_standard_fields_not_duplicated(self):
        """Internal logging attributes should not bleed into output JSON."""
        fmt = JSONFormatter()
        record = self._make_record("msg")
        data = json.loads(fmt.format(record))
        # These are internal log record attrs — must not appear in output body
        for internal_key in ("msg", "args", "levelno", "pathname", "lineno"):
            assert internal_key not in data


# ── EngagementFilter ───────────────────────────────────────────────────────────


class TestEngagementFilter:
    def test_injects_engagement_id(self):
        flt = EngagementFilter("eng-abc-123")
        record = logging.LogRecord("cna.test", logging.INFO, "", 0, "msg", (), None)
        assert flt.filter(record) is True
        assert record.engagement_id == "eng-abc-123"

    def test_does_not_overwrite_existing_engagement_id(self):
        """If engagement_id already on record (from nested filter), leave it alone."""
        flt = EngagementFilter("new-id")
        record = logging.LogRecord("cna.test", logging.INFO, "", 0, "msg", (), None)
        record.engagement_id = "original-id"
        flt.filter(record)
        assert record.engagement_id == "original-id"

    def test_always_returns_true(self):
        """Filter must never suppress records."""
        flt = EngagementFilter("x")
        record = logging.LogRecord("cna.test", logging.DEBUG, "", 0, "msg", (), None)
        assert flt.filter(record) is True


# ── setup_logging ──────────────────────────────────────────────────────────────


class TestSetupLogging:
    def teardown_method(self):
        """Clear cna logger state between tests."""
        logger = logging.getLogger("cna")
        logger.handlers.clear()
        logger.filters.clear()

    def test_setup_logging_no_args_adds_handler(self):
        setup_logging()
        logger = logging.getLogger("cna")
        assert len(logger.handlers) >= 1

    def test_setup_logging_with_engagement_id_adds_filter(self):
        setup_logging(engagement_id="eng-test-001")
        logger = logging.getLogger("cna")
        assert any(isinstance(f, EngagementFilter) for f in logger.filters)

    def test_setup_logging_without_engagement_id_no_filter(self):
        setup_logging()
        logger = logging.getLogger("cna")
        assert not any(isinstance(f, EngagementFilter) for f in logger.filters)

    def test_setup_logging_respects_log_level_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CNA_LOG_LEVEL", "DEBUG")
        setup_logging()
        logger = logging.getLogger("cna")
        assert logger.level == logging.DEBUG

    def test_setup_logging_invalid_level_falls_back_to_info(self, monkeypatch):
        monkeypatch.setenv("CNA_LOG_LEVEL", "NOTAVALIDLEVEL")
        setup_logging()
        logger = logging.getLogger("cna")
        # getattr on unknown level returns INFO (10 is DEBUG, 20 is INFO)
        assert logger.level == logging.INFO

    def test_setup_logging_with_log_dir_creates_file_handler(self, tmp_path):
        log_dir = tmp_path / "logs"
        setup_logging(log_dir=log_dir)
        logger = logging.getLogger("cna")
        file_handlers = [h for h in logger.handlers if hasattr(h, "baseFilename")]
        assert len(file_handlers) == 1
        assert (log_dir / "cna.log").exists() or log_dir.exists()

    def test_setup_logging_clears_existing_handlers(self):
        """Calling setup_logging twice should not accumulate handlers."""
        setup_logging()
        setup_logging()
        logger = logging.getLogger("cna")
        # Should not have doubled up
        assert len(logger.handlers) <= 2  # console, maybe file

    def test_setup_logging_falls_back_without_rich(self, monkeypatch):
        """If Rich is not installed, should fall back to StreamHandler gracefully."""
        import builtins

        real_import = builtins.__import__

        def import_blocker(name, *args, **kwargs):
            if name == "rich.logging":
                raise ImportError("rich not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", import_blocker)
        setup_logging()  # Must not raise
        logger = logging.getLogger("cna")
        assert len(logger.handlers) >= 1


# ── get_logger ─────────────────────────────────────────────────────────────────


class TestGetLogger:
    def test_returns_logger_with_cna_prefix(self):
        logger = get_logger("modules.network")
        assert logger.name == "cna.modules.network"

    def test_does_not_double_prefix_if_already_cna(self):
        logger = get_logger("cna.modules.network")
        assert logger.name == "cna.modules.network"

    def test_returns_logging_logger_instance(self):
        logger = get_logger("test.component")
        assert isinstance(logger, logging.Logger)
