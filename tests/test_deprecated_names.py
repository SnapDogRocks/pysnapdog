# SPDX-License-Identifier: Apache-2.0
"""The package must not read or send the names the server has deprecated.

The server keeps ``id`` of a playlist (``PlaylistInfo``, ``PlaylistDetails``, the play body) and
``playlist`` of ``zone_changed`` until 1.0 and replaces them by ``index``, ``playlist_index`` and
``playlist_id``. A source file that uses one of them as a key or an attribute is a bug, except at
the one documented fallback for older servers, ``_playlist_index``. Strings that are only values
(``RepeatMode.PLAYLIST = "playlist"``) do not count.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pysnapdog

PACKAGE = Path(pysnapdog.__file__).resolve().parent
DEPRECATED = frozenset({"id", "playlist"})
FALLBACK = "_playlist_index"
# The only places that may name a deprecated field: (file, the field), both arguments of
# ``_playlist_index``. Adding to this set needs a reason in the review.
# ``MediaTrack.id`` is the id of a track, a string, and not deprecated.
OTHER_IDS = frozenset({"MediaTrack"})
ALLOWED = {("models.py", "id"), ("events.py", "playlist")}


def _keys(tree: ast.AST) -> list[ast.AST]:
    """The nodes that read or write a field by name: ``d["id"]``, ``{"id": ...}``, ``f("id")``,
    ``f(id=...)`` and ``x.id``. A string that is only a value, such as an enum member, is not one.
    """
    found: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            found.append(node.slice)
        elif isinstance(node, ast.Dict):
            found.extend(key for key in node.keys if key is not None)
        elif isinstance(node, ast.Call):
            found.extend(node.args)
            found.extend(node.keywords)
        elif isinstance(node, ast.Attribute):
            found.append(node)
    return found


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.keyword):
        return node.arg
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def scan(source: str, filename: str) -> tuple[list[str], set[tuple[str, str]]]:
    """Deprecated names used in ``source``, and those used only as arguments of the fallback."""
    tree = ast.parse(source, filename=filename)
    bad: list[str] = []
    fallback: set[tuple[str, str]] = set()
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in OTHER_IDS:
            allowed.update(id(inner) for inner in ast.walk(node))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == FALLBACK:
            for arg in node.args:
                if _name(arg) in DEPRECATED:
                    fallback.add((filename, str(_name(arg))))
                    allowed.add(id(arg))
    for node in _keys(tree):
        name = _name(node)
        if name in DEPRECATED and id(node) not in allowed:
            bad.append(f"{filename}:{getattr(node, 'lineno', '?')}: {name!r}")
    return bad, fallback


def _scan_package() -> tuple[list[str], set[tuple[str, str]]]:
    bad: list[str] = []
    fallback: set[tuple[str, str]] = set()
    for path in sorted(PACKAGE.glob("*.py")):
        found, used = scan(path.read_text(), path.name)
        bad += found
        fallback |= used
    return bad, fallback


def test_no_source_file_reads_or_sends_a_deprecated_name() -> None:
    bad, _ = _scan_package()
    assert bad == []


def test_the_fallback_for_older_servers_is_the_only_exception() -> None:
    _, fallback = _scan_package()
    assert fallback == ALLOWED


def test_the_scan_finds_every_way_of_using_a_deprecated_name() -> None:
    source = (
        'a = data["id"]\n'
        'b = {"id": 1}\n'
        'c = data.get("playlist")\n'
        "d = Model(id=1)\n"
        "e = zone.playlist\n"
        'f = _playlist_index(data, "index", "id", what)\n'
        'g = "playlist"\n'
    )
    bad, fallback = scan(source, "x.py")
    assert len(bad) == 5
    assert fallback == {("x.py", "id")}
