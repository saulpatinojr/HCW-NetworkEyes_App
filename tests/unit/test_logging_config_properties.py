"""Property-based tests for structured-log capture via ``JSONFormatter``.

Feature: production-readiness
Property 16: Emitted errors are captured as structured logs

For any error event emitted by a reviewed service, the produced log record
parses as a structured record carrying at least a level and a message field.
The core engine's ``cna.core.logging_config.JSONFormatter`` renders every log
record as a single line of JSON, so for any message, level, and set of extra
fields the formatter output always parses as JSON and always carries a
non-empty ``level`` and a ``message`` field.

Validates: Requirements 8.2
"""

from __future__ import annotations

import json
import logging

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.core.logging_config import JSONFormatter

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=200)

# The standard logging levels a reviewed service can emit. Error events use
# ERROR/CRITICAL, but the structured-capture invariant holds for every level.
_LEVEL = st.sampled_from(
    [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ]
)

# Arbitrary log messages, including empty strings and text with characters that
# must survive JSON serialization (quotes, braces, newlines, unicode).
_MESSAGE = st.text()

# Reserved names an ``extra={...}`` key must not collide with. Two overlapping
# classes:
#   * the JSONFormatter output keys (message/level/logger/timestamp) — an extra
#     field named after one of these would overwrite the rendered value (e.g.
#     'levelname' rewrites the emitted level, breaking the level assertion); and
#   * the ``logging.LogRecord`` attribute names — ``logger.makeRecord`` raises
#     KeyError for an ``extra`` key that shadows an existing record attribute
#     (name/msg/args/…), so generating one is a test-generator bug, not a
#     property counter-example.
# Excluding both keeps the generator inside the real input space of an ``extra``
# dict a service can actually pass.
_RESERVED_EXTRA_KEYS = frozenset(
    {
        # JSONFormatter output keys.
        "message",
        "level",
        "logger",
        "timestamp",
        # logging.LogRecord reserved attribute names.
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "asctime",
    }
)


def _is_valid_extra_key(key: str) -> bool:
    """True for a key a service could realistically pass in ``extra={...}``.

    A valid ``extra`` key is a plain identifier that is neither a reserved
    logging/formatter name nor a dunder (``__dict__``/``__class__``/… would
    collide with object attributes and break ``setattr``/``makeRecord`` — a
    generator artifact, not a property counter-example).
    """
    if not key.isidentifier() or key in _RESERVED_EXTRA_KEYS:
        return False
    return not (key.startswith("__") and key.endswith("__"))


# Arbitrary extra fields merged into the record via ``extra={...}``. Keys avoid
# the reserved logging/formatter names above; values are JSON-serializable scalars.
_EXTRA = st.dictionaries(
    keys=st.text(min_size=1).filter(_is_valid_extra_key),
    values=st.one_of(
        st.text(),
        st.integers(),
        st.booleans(),
        st.none(),
        st.floats(allow_nan=False, allow_infinity=False),
    ),
    max_size=5,
)


def _make_record(msg: str, level: int, extra: dict[str, object]) -> logging.LogRecord:
    """Build a log record the way the stdlib logging machinery would."""
    record = logging.LogRecord(
        name="cna.test",
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, val in extra.items():
        setattr(record, key, val)
    return record


@_PROPERTY_SETTINGS
@given(message=_MESSAGE, level=_LEVEL, extra=_EXTRA)
def test_property16_records_parse_as_structured_logs(
    message: str,
    level: int,
    extra: dict[str, object],
) -> None:
    """Feature: production-readiness, Property 16: Emitted errors are captured as structured logs.

    For any message, level, and extra fields, the formatter output parses as
    JSON and carries at least a non-empty ``level`` and a ``message`` field.
    """
    formatter = JSONFormatter()
    record = _make_record(message, level, extra)

    output = formatter.format(record)

    # Always a single line of JSON — structured ingestion consumes one record
    # per line, so the output must not contain embedded newlines.
    assert "\n" not in output

    parsed = json.loads(output)
    assert isinstance(parsed, dict)

    # Carries at least a level and a message field.
    assert "level" in parsed
    assert "message" in parsed
    assert parsed["level"] == logging.getLevelName(level)
    assert parsed["level"]  # non-empty level string
    assert parsed["message"] == message


@_PROPERTY_SETTINGS
@given(message=_MESSAGE, extra=_EXTRA)
def test_property16_error_events_carry_level_and_message(
    message: str,
    extra: dict[str, object],
) -> None:
    """Feature: production-readiness, Property 16: Emitted errors are captured as structured logs.

    An error event routed through a real logger + the ``JSONFormatter`` always
    parses as a structured record carrying at least a level and a message field.
    """
    formatter = JSONFormatter()
    # Route through a real logger to exercise the emit path a service uses.
    logger = logging.getLogger("cna.test.property16")
    record = logger.makeRecord(
        logger.name,
        logging.ERROR,
        "",
        0,
        message,
        (),
        None,
        extra=extra or None,
    )

    parsed = json.loads(formatter.format(record))

    assert parsed["level"] == "ERROR"
    assert parsed["message"] == message
    assert isinstance(parsed["level"], str) and parsed["level"]
