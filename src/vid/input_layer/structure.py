"""Flattening of structure (the PSE guard reference Sec 3): content inside JSON,
XML, Markdown or a graph of nodes is taken out of its wrapper and read as
plain text. Codes E-18, E-25, E-27, E-50."""

from __future__ import annotations

import html
import json
import re

from vid.input_layer.types import Finding, short


def _strings(value, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and len(k) > 24:
                out.append(k)          # long keys can carry text too
            _strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out)


def _json_blocks(text: str):
    """Top-level JSON objects/arrays inside text, as (span, value)."""
    i = 0
    while i < len(text):
        if text[i] in "{[":
            try:
                value, end = json.JSONDecoder().raw_decode(text, i)
            except ValueError:
                i += 1
                continue
            if isinstance(value, (dict, list)) and end - i >= 8:
                yield (i, end), value
                i = end
                continue
        i += 1


def json_flat(text: str) -> tuple[str, list[Finding]]:
    pieces, spans = [], []
    for span, value in _json_blocks(text):
        strings: list[str] = []
        _strings(value, strings)
        if any(len(s) >= 3 for s in strings):
            spans.append((span, "\n".join(strings)))
            pieces.extend(strings)
    if not spans:
        return text, []
    out, last = [], 0
    for (a, b), flat in spans:
        out.append(text[last:a])
        out.append(flat)
        last = b
    out.append(text[last:])
    res = "".join(out)
    return res, [Finding("PIT-E-25", f"Text inside JSON taken out of its wrapper ({len(pieces)} string(s)).",
                         short(text[spans[0][0][0]:spans[0][0][1]]), short(" | ".join(pieces)), count=len(pieces))]


_XML_HINT = re.compile(r"<\?xml|<([A-Za-z_][\w.\-:]*)(?:\s[^<>]*)?>.*?</\1\s*>", re.S)
_TAG = re.compile(r"<[^<>]+>")


def xml_flat(text: str) -> tuple[str, list[Finding]]:
    if not _XML_HINT.search(text):
        return text, []
    hidden = []
    for m in re.finditer(r"<!--(.*?)-->", text, re.S):
        hidden.append(m.group(1).strip())
    for m in re.finditer(r"<!\[CDATA\[(.*?)\]\]>", text, re.S):
        hidden.append(m.group(1).strip())
    for m in re.finditer(r"\s[\w:\-]+\s*=\s*(\"[^\"]*\"|'[^']*')", text):
        v = m.group(1)[1:-1].strip()
        if len(v) >= 12 and " " in v:
            hidden.append(v)
    body = re.sub(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>", " ", text, flags=re.S)
    body = html.unescape(_TAG.sub(" ", body))
    body = re.sub(r"[ \t]+", " ", body).strip()
    res = "\n".join([body, *hidden]).strip()
    detail = "Text inside XML/HTML tags taken out of its wrapper"
    if hidden:
        detail += f"; {len(hidden)} comment(s), CDATA or attribute text included"
    return res, [Finding("PIT-E-50", detail + ".", short(text), short(res), count=max(1, len(hidden)))]


def markdown_flat(text: str) -> tuple[str, list[Finding]]:
    hidden = []
    hidden += [m.group(1).strip() for m in re.finditer(r"<!--(.*?)-->", text, re.S)]
    hidden += [m.group(1).strip() for m in re.finditer(r"!\[([^\]]+)\]\([^)]*\)", text)]          # image alt text
    hidden += [m.group(1) for m in re.finditer(r"\]\([^)\s]*\s+\"([^\"]+)\"\)", text)]            # link / image titles
    hidden += [m.group(2).strip() for m in re.finditer(r"(?m)^\s*\[([^\]^]+)\]:\s*\S+(?:\s+[\"'(](.+?)[\"')])?\s*$", text) if m.group(2)]
    hidden += [m.group(1).strip() for m in re.finditer(r"(?m)^\s*\[\^[^\]]+\]:\s*(.+)$", text)]   # footnotes
    hidden += [m.group(1).strip() for m in re.finditer(r"\[[^\]]*\]:\s*#\s*\((.*?)\)", text)]    # [//]: # (comment)
    md_like = re.search(r"(?m)^#{1,6}\s|\*\*.+?\*\*|\[[^\]]+\]\([^)]+\)|^```|^\s*[-*]\s", text)
    if not hidden or not (md_like or "<!--" in text or "![" in text or re.search(r"(?m)^\s*\[[^\]]+\]:", text)):
        return text, []
    body = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)
    body = re.sub(r"(?m)^\s*\[[^\]]+\]:.*$", "", body)
    body = re.sub(r"[*_`#>]+", "", body).strip()
    res = "\n".join([body, *hidden]).strip()
    return res, [Finding("PIT-E-27", f"Markdown read as plain text; {len(hidden)} hidden part(s) (comments, alt text, titles, references) included.",
                         short(text), short(" | ".join(hidden)), count=len(hidden))]


def graph_flat(text: str) -> tuple[str, list[Finding]]:
    labels = []
    if re.search(r"\b(?:di)?graph\s*\w*\s*\{", text) and re.search(r"->|--", text):          # Graphviz DOT
        labels += re.findall(r"label\s*=\s*\"((?:[^\"\\]|\\.)*)\"", text)
        labels += [a for a in re.findall(r"\"((?:[^\"\\]|\\.){3,})\"\s*(?:->|--|\[|;)", text) if a not in labels]
    if re.search(r"(?m)^\s*(?:graph|flowchart)\s+(?:TD|TB|BT|RL|LR)\b", text):              # Mermaid
        labels += re.findall(r"\w+\s*[\[\(\{>]{1,2}\"?([^\]\)\}\"]+?)\"?[\]\)\}]{1,2}", text)
        labels += re.findall(r"--\s*\"?([^\-\">|]+?)\"?\s*-->", text)
        labels += re.findall(r"-->\|([^|]+)\|", text)
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and ("nodes" in data or "edges" in data):
        for key in ("nodes", "edges", "links"):
            for item in data.get(key, []) or []:
                if isinstance(item, dict):
                    labels += [str(v) for k, v in item.items() if k in ("label", "text", "name", "title", "content", "data") and isinstance(v, (str, int))]
    labels = [l.strip() for l in labels if l and l.strip()]
    if not labels:
        return text, []
    res = "\n".join(labels)
    return res, [Finding("PIT-E-18", f"Text from {len(labels)} graph node(s) and edge(s) read in order.", short(text), short(" | ".join(labels)), count=len(labels))]


def flatten(text: str) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    for fn in (graph_flat, json_flat, xml_flat, markdown_flat):
        new, f = fn(text)
        if f:
            findings.extend(f)
            text = new
    return text, findings
