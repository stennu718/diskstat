import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from diskstat import build_flat, render_html


def test_render_html_uses_addEventListener(tmp_path, sample_tree):
    tree = sample_tree
    flat = build_flat(tree, max_nodes=10)
    htmlp = tmp_path / "addEventListener.html"
    csvp = tmp_path / "addEventListener.csv"
    render_html(tree, flat, str(htmlp), str(csvp))
    text = htmlp.read_text(encoding="utf-8")
    assert "addEventListener" in text
    assert "window.open" in text
    assert "notes.txt" in text


def test_render_html_includes_flat_json_and_legend(tmp_path, sample_tree):
    tree = sample_tree
    flat = build_flat(tree, max_nodes=10)
    htmlp = tmp_path / "flat.html"
    csvp = tmp_path / "flat.csv"
    render_html(tree, flat, str(htmlp), str(csvp))
    text = htmlp.read_text(encoding="utf-8")
    assert "d3.v7.min.js" in text
    assert "treemap" in text
    assert "legend" in text
    # flat must be serialized into the page so JS can consume it.
    serialized = "const flat = " + json.dumps(flat, ensure_ascii=False)
    assert serialized in text
