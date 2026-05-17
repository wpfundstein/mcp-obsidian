"""Tests for str_replace unique-match substring replacement."""

import pytest
from unittest.mock import MagicMock, patch

from mcp_obsidian.obsidian import Obsidian


def _make_obsidian():
    return Obsidian(api_key="test-key", protocol="http", host="localhost", port=27123)


def _ok_response():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    return resp


def _get_response(text: str):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.text = text
    return resp


def test_str_replace_unique_match():
    """Single occurrence: GET once, PUT once with the replaced body as UTF-8 bytes."""
    api = _make_obsidian()
    original = "Status: [ ] Test-UAP bestellt\n"
    expected = "Status: [x] Test-UAP bestellt\n"

    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response(original)) as mock_get, \
         patch("mcp_obsidian.obsidian.requests.put", return_value=_ok_response()) as mock_put:
        api.str_replace("plan.md", "[ ] Test-UAP", "[x] Test-UAP")
        assert mock_get.call_count == 1
        assert mock_put.call_count == 1
        sent = mock_put.call_args.kwargs["data"]
        assert sent == expected.encode("utf-8")


def test_str_replace_not_found_raises_no_put():
    """Missing target: raises with 'String not found', NO PUT issued."""
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response("nothing matches here")), \
         patch("mcp_obsidian.obsidian.requests.put") as mock_put:
        with pytest.raises(Exception, match="String not found"):
            api.str_replace("f.md", "absent", "replacement")
        mock_put.assert_not_called()


def test_str_replace_ambiguous_raises_no_put():
    """Multiple occurrences: raises with the count, NO PUT issued."""
    api = _make_obsidian()
    content = "TODO item one\nTODO item two\n"
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response(content)), \
         patch("mcp_obsidian.obsidian.requests.put") as mock_put:
        with pytest.raises(Exception, match="appears 2 times"):
            api.str_replace("f.md", "TODO", "DONE")
        mock_put.assert_not_called()


def test_str_replace_idempotent_when_equal():
    """old_str == new_str AND present: GET once, NO PUT, no exception."""
    api = _make_obsidian()
    content = "Already correct value\n"
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response(content)) as mock_get, \
         patch("mcp_obsidian.obsidian.requests.put") as mock_put:
        api.str_replace("f.md", "correct", "correct")
        assert mock_get.call_count == 1
        mock_put.assert_not_called()


def test_str_replace_idempotent_equal_but_not_in_file():
    """old_str == new_str BUT absent: raises (no silent success)."""
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response("unrelated content")), \
         patch("mcp_obsidian.obsidian.requests.put") as mock_put:
        with pytest.raises(Exception, match="String not found"):
            api.str_replace("f.md", "missing", "missing")
        mock_put.assert_not_called()


def test_str_replace_unicode_roundtrip():
    """Unicode old/new: PUT body is exact UTF-8 bytes; charset header is set."""
    api = _make_obsidian()
    original = "Größe für Müller — alte Version 🚀\n"
    expected = "Größe für Müller — neue Version 🎯\n"

    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response(original)), \
         patch("mcp_obsidian.obsidian.requests.put", return_value=_ok_response()) as mock_put:
        api.str_replace("f.md", "alte Version 🚀", "neue Version 🎯")
        kwargs = mock_put.call_args.kwargs
        assert kwargs["data"] == expected.encode("utf-8")
        assert isinstance(kwargs["data"], (bytes, bytearray))
        assert kwargs["headers"]["Content-Type"] == "text/markdown; charset=utf-8"


def test_str_replace_multiline_with_context():
    """Multiline old_str: newlines and surrounding context are honored verbatim."""
    api = _make_obsidian()
    original = (
        "## Phase 2\n"
        "- [ ] Punkt 1\n"
        "- [ ] Punkt 2\n"
        "- [ ] Punkt 3\n"
        "\n"
        "Footer\n"
    )
    old_block = "- [ ] Punkt 2\n- [ ] Punkt 3\n"
    new_block = "- [x] Punkt 2\n"
    expected = (
        "## Phase 2\n"
        "- [ ] Punkt 1\n"
        "- [x] Punkt 2\n"
        "\n"
        "Footer\n"
    )

    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response(original)), \
         patch("mcp_obsidian.obsidian.requests.put", return_value=_ok_response()) as mock_put:
        api.str_replace("plan.md", old_block, new_block)
        assert mock_put.call_args.kwargs["data"] == expected.encode("utf-8")


def test_str_replace_preserves_rest_of_file():
    """Replacement happens only at the target; everything before and after is byte-identical."""
    api = _make_obsidian()
    head = "# Title\n\n" + ("Filler line\n" * 100)
    target_old = "MARKER_OLD"
    target_new = "MARKER_NEW"
    tail = "\n\nFooter section\n" + ("More filler\n" * 50)
    original = head + target_old + tail
    expected = head + target_new + tail

    with patch("mcp_obsidian.obsidian.requests.get", return_value=_get_response(original)), \
         patch("mcp_obsidian.obsidian.requests.put", return_value=_ok_response()) as mock_put:
        api.str_replace("f.md", target_old, target_new)
        sent = mock_put.call_args.kwargs["data"]
        assert sent == expected.encode("utf-8")
        assert sent.startswith(head.encode("utf-8"))
        assert sent.endswith(tail.encode("utf-8"))
