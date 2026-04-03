"""Tests for the Tinker unified query parser."""

import pytest

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, TextFilter
from tinker.query.parser import parse


def test_wildcard():
    assert parse("*") == TextFilter(text="*", exact=False)


def test_empty():
    assert parse("") == TextFilter(text="*", exact=False)


def test_bare_word():
    assert parse("timeout") == TextFilter(text="timeout", exact=False)


def test_quoted_string():
    node = parse('"connection timeout"')
    assert isinstance(node, TextFilter)
    assert node.text == "connection timeout"
    assert node.exact is True


def test_field_simple():
    node = parse("level:ERROR")
    assert isinstance(node, FieldFilter)
    assert node.field == "level"
    assert node.values == ["ERROR"]


def test_field_alias_normalised():
    node = parse("severity:ERROR")
    assert isinstance(node, FieldFilter)
    assert node.field == "level"   # normalised via FIELD_ALIASES


def test_field_multi_value():
    node = parse("level:(ERROR OR WARN)")
    assert isinstance(node, FieldFilter)
    assert node.field == "level"
    assert set(node.values) == {"ERROR", "WARN"}


def test_and_explicit():
    node = parse('level:ERROR AND "timeout"')
    assert isinstance(node, AndExpr)
    assert isinstance(node.left, FieldFilter)
    assert isinstance(node.right, TextFilter)


def test_and_implicit():
    node = parse('level:ERROR "timeout"')
    assert isinstance(node, AndExpr)


def test_or():
    node = parse("level:ERROR OR level:WARN")
    assert isinstance(node, OrExpr)


def test_not():
    node = parse('NOT "health check"')
    assert isinstance(node, NotExpr)
    assert isinstance(node.operand, TextFilter)


def test_nested():
    node = parse('(level:ERROR OR level:WARN) AND "database"')
    assert isinstance(node, AndExpr)
    assert isinstance(node.left, OrExpr)
    assert isinstance(node.right, TextFilter)


def test_complex():
    node = parse('level:ERROR AND NOT "test" AND service:payments-api')
    # Should parse without errors; shape is ANDs
    assert isinstance(node, AndExpr)


def test_invalid_unclosed_paren():
    with pytest.raises((ValueError, Exception)):
        parse("level:(ERROR OR WARN")
