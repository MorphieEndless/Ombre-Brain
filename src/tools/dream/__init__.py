"""
========================================
tools/dream/__init__.py — dream 工具入口
========================================

dream 是「我做一次梦——读最近 N 小时内有变动的所有桶，自己沉进去想
一遍」。这里把整个流程拆成三步：
1. candidates.py：筛选窗口内的桶 + 软上限
2. hints.py：连接提示 + 结晶提示
3. inspiration.py：仅在显式 inspiration=True 时读取已落盘向量，生成响应态候选
4. output.py：拼最终文本（包含 active plan 段、feel 历史段）

dispatch() 只负责把这三步串起来。

对外暴露：dispatch(window_hours, inspiration=False) → str
========================================
"""

from typing import Optional

from .. import _runtime as rt
from .candidates import collect_candidates, collect_core_context
from .hints import build_connection_hint, build_crystal_hint
from .inspiration import InspirationResult, build_inspiration_candidates
from .output import format_dream_output


async def dispatch(
    window_hours: Optional[int] = 48,
    inspiration: bool = False,
) -> str:
    if type(inspiration) is not bool:
        raise ValueError("inspiration must be a boolean")

    await rt.decay_engine.ensure_started()

    try:
        all_buckets = await rt.bucket_mgr.list_all(include_archive=False)
    except Exception as e:
        rt.logger.error(f"Dream failed to list buckets: {e}")
        return "记忆系统暂时无法访问。"

    window_hours = max(1, min(int(window_hours or 48), 24 * 14))
    recent = collect_candidates(all_buckets, window_hours)
    core_context = collect_core_context(all_buckets)
    if not recent and not core_context:
        return f"过去 {window_hours} 小时内没有需要消化的新记忆。"

    connection_hint = await build_connection_hint(recent)
    crystal_hint = await build_crystal_hint(all_buckets)
    inspiration_result = None
    if inspiration:
        try:
            inspiration_result = await build_inspiration_candidates(
                recent=recent,
                all_buckets=all_buckets,
                embedding_engine=rt.embedding_engine,
            )
        except Exception as exc:
            rt.logger.warning(
                "Dream inspiration candidate generation failed: %s",
                type(exc).__name__,
            )
            inspiration_result = InspirationResult(
                "unavailable",
                "candidate_generation_failed",
            )

    final_text = format_dream_output(
        recent=recent,
        all_buckets=all_buckets,
        window_hours=window_hours,
        connection_hint=connection_hint,
        crystal_hint=crystal_hint,
        core_context=core_context,
        inspiration_result=inspiration_result,
    )

    if rt.fire_webhook:
        await rt.fire_webhook("dream", {"recent": len(recent), "chars": len(final_text)})
    return final_text
