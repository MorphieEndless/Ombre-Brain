"""不可变原文证据存储。

原文按 UTF-8 内容哈希写入 ``<vault>/_sources/src_<sha256>.source``。
文件不参与普通 Markdown 扫描、浮现或 GitHub 同步；只有 source_read 在
精确匹配桶 ID 与标题后才会读取。
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SOURCE_REF_RE = re.compile(r"^src_[0-9a-f]{64}$")
MAX_SOURCE_REFS = 32
MAX_SOURCE_RANGES = 128


def normalize_source_ranges(value: Any) -> list[list[int]]:
    """规范化为 1-based、闭区间、互不重叠的行范围。"""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("source_ranges 必须是 [[起始行, 结束行], ...]")
    if len(value) > MAX_SOURCE_RANGES:
        raise ValueError(f"source_ranges 过多（{len(value)} > {MAX_SOURCE_RANGES}）")
    ranges: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("source_ranges 每项必须包含起始行和结束行")
        try:
            start, end = int(item[0]), int(item[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("source_ranges 行号必须是整数") from exc
        if start < 1 or end < start:
            raise ValueError("source_ranges 必须使用 1-based 闭区间，且结束行不小于起始行")
        ranges.append((start, end))
    ranges.sort()
    merged: list[list[int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def normalize_source_refs(value: Any) -> list[dict[str, Any]]:
    """校验并去重桶 frontmatter 中的原文引用。"""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("source_refs 必须是列表")
    if len(value) > MAX_SOURCE_REFS:
        raise ValueError(f"source_refs 过多（{len(value)} > {MAX_SOURCE_REFS}）")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[tuple[int, int], ...]]] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("source_refs 每项必须是对象")
        ref = str(item.get("ref") or "").strip()
        if not SOURCE_REF_RE.fullmatch(ref):
            raise ValueError("source_refs 包含非法 ref")
        ranges = normalize_source_ranges(item.get("ranges"))
        key = (ref, tuple((pair[0], pair[1]) for pair in ranges))
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"ref": ref, "ranges": ranges})
    return normalized


class SourceStore:
    """内容寻址的只增不改原文层。"""

    def __init__(self, vault_dir: str | Path, max_bytes: int = 2 * 1024 * 1024):
        self.root = Path(vault_dir).resolve() / "_sources"
        self.max_bytes = max(0, int(max_bytes))

    def put(self, content: str) -> str:
        raw = str(content).encode("utf-8")
        if not raw:
            raise ValueError("原文为空")
        if self.max_bytes and len(raw) > self.max_bytes:
            raise ValueError(
                f"原文过大（{len(raw) / 1024:.1f} KB > 上限 {self.max_bytes / 1024:.0f} KB）"
            )
        digest = hashlib.sha256(raw).hexdigest()
        ref = f"src_{digest}"
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{ref}.source"
        if target.exists():
            if target.read_bytes() != raw:
                raise OSError("原文哈希冲突或现有证据文件已损坏")
            return ref

        fd, temp_name = tempfile.mkstemp(prefix=".source-", dir=str(self.root))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_name, target)
            except FileExistsError:
                if target.read_bytes() != raw:
                    raise OSError("原文哈希冲突或并发写入结果不一致")
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
        return ref

    def read(self, ref: str) -> str:
        ref = str(ref).strip()
        if not SOURCE_REF_RE.fullmatch(ref):
            raise ValueError("非法 source_ref")
        target = self.root / f"{ref}.source"
        raw = target.read_bytes()
        expected = ref.removeprefix("src_")
        if hashlib.sha256(raw).hexdigest() != expected:
            raise OSError("原文证据完整性校验失败")
        return raw.decode("utf-8")

    @staticmethod
    def select_ranges(content: str, ranges: list[list[int]]) -> str:
        normalized = normalize_source_ranges(ranges)
        if not normalized:
            return content
        lines = content.splitlines(keepends=True)
        selected: list[str] = []
        for start, end in normalized:
            if start > len(lines):
                continue
            selected.extend(lines[start - 1 : min(end, len(lines))])
        return "".join(selected)
