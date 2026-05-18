from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_WS_RE = re.compile(r"\s+")


@dataclass
class ReportMeta:
    title: str
    meta: Dict[str, str]
    headings: List[Dict[str, Any]]
    text_stats: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "report.meta.v1",
            "title": self.title,
            "meta": dict(self.meta),
            "headings": list(self.headings),
            "text_stats": dict(self.text_stats),
        }


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self.title_parts: List[str] = []
        self.meta: Dict[str, str] = {}
        self.headings: List[Dict[str, Any]] = []
        self._in_heading: Optional[str] = None
        self._heading_parts: List[str] = []
        self.text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = (tag or "").lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs if k}
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            name = (attr_map.get("name") or attr_map.get("property") or "").strip()
            content = (attr_map.get("content") or "").strip()
            if name and content:
                self.meta[name] = content
            return
        if tag in {"h1", "h2", "h3"}:
            self._in_heading = tag
            self._heading_parts = []
            return

    def handle_endtag(self, tag: str) -> None:
        tag = (tag or "").lower()
        if tag == "title":
            self._in_title = False
            return
        if tag in {"h1", "h2", "h3"} and self._in_heading == tag:
            text = _WS_RE.sub(" ", "".join(self._heading_parts)).strip()
            if text:
                self.headings.append({"level": tag, "text": text})
            self._in_heading = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        text = str(data or "")
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._in_heading is not None:
            self._heading_parts.append(text)
        self.text_parts.append(text)


def extract_report_meta_from_html(html: str) -> ReportMeta:
    parser = _MetaParser()
    parser.feed(str(html or ""))
    title = _WS_RE.sub(" ", "".join(parser.title_parts)).strip()
    full_text = _WS_RE.sub(" ", "".join(parser.text_parts)).strip()
    word_like = [seg for seg in re.split(r"[\s，。；、,.!?]+", full_text) if seg]
    text_stats = {
        "char_count": len(full_text),
        "token_count_rough": len(word_like),
        "heading_count": len(parser.headings),
        "h1_count": sum(1 for h in parser.headings if h.get("level") == "h1"),
        "h2_count": sum(1 for h in parser.headings if h.get("level") == "h2"),
        "h3_count": sum(1 for h in parser.headings if h.get("level") == "h3"),
    }
    return ReportMeta(
        title=title,
        meta=dict(parser.meta),
        headings=list(parser.headings),
        text_stats=text_stats,
    )


def extract_report_meta_from_file(html_path: Path) -> ReportMeta:
    path = Path(html_path)
    html = path.read_text(encoding="utf-8", errors="ignore")
    return extract_report_meta_from_html(html)


def write_report_meta_json(html_path: Path, *, output_path: Optional[Path] = None) -> Path:
    meta = extract_report_meta_from_file(html_path)
    out = Path(output_path) if output_path is not None else Path(html_path).with_suffix(".meta.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


__all__ = [
    "ReportMeta",
    "extract_report_meta_from_file",
    "extract_report_meta_from_html",
    "write_report_meta_json",
]

