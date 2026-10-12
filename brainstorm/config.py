"""配置加载：config.json（本机，不进 git）+ config.local.json（凭据，不进 git）。

仓库只提供 config.example.json / config.local.json.example 占位模板。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load_json(path, required=False):
    if not os.path.exists(path):
        if required:
            raise FileNotFoundError("config not found: %s" % path)
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_config(path=None, with_local=True):
    path = os.path.abspath(path or os.path.join(ROOT, "config.json"))
    cfg = _load_json(path, required=True)
    cfg["_path"] = path
    cfg["_dir"] = os.path.dirname(path)
    if with_local:
        cfg["_local"] = _load_json(os.path.join(cfg["_dir"], "config.local.json"))
    else:
        cfg["_local"] = {}
    return cfg


def local(cfg, section, key=None, default=None):
    node = (cfg.get("_local") or {}).get(section)
    if node is None:
        return default
    if key is None:
        return node
    return node.get(key, default)


def room_path(cfg):
    rel = (cfg.get("room") or {}).get("file") or "room.jsonl"
    return rel if os.path.isabs(rel) else os.path.join(cfg["_dir"], rel)


def redact(text, cfg):
    keys = (cfg.get("log") or {}).get("redact") or []
    if not isinstance(text, str) or not text:
        return text
    out = text
    for k in keys:
        if not k:
            continue
        out = re.sub(
            r"(?i)(%s[\"']?\s*[:=]\s*[\"']?)([^\s\"',;}]+)" % re.escape(k),
            lambda m: m.group(1) + "***",
            out,
        )
        out = re.sub(
            r"(?i)(\b%s\b\s+)([A-Za-z0-9_\-\.]{8,})" % re.escape(k),
            lambda m: m.group(1) + "***",
            out,
        )
    return out
