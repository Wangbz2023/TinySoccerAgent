"""CLI 层：暴露 ingest、run-one、eval 和训练数据导出命令。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .agents import CommentaryHarness
from .ingest import iter_match_records
from .memory import SQLiteMemory
from .schemas import EventPacket


DEFAULT_DB = "artifacts/tiny_soccer_agent.db"
DEFAULT_TAR = "database/Game_dataset.tar.gz"
DEFAULT_INDEX = "database/Game_dataset_csv/game_database.csv"
# 面试 demo 优先覆盖这些高价值事件类型，避免一上来展示大量 unknown 普通事件。
DEMO_EVENT_TYPES = ["goal", "yellow_card", "red_card", "corner", "substitution"]


def main(argv: List[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="TinySoccerAgent 事件驱动足球解说智能体编排框架")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="将本地比赛 JSON 规范化写入 SQLite memory")
    ingest_parser.add_argument("--tar", default=DEFAULT_TAR, help="Game_dataset.tar.gz 路径")
    ingest_parser.add_argument("--index", default=DEFAULT_INDEX, help="game_database.csv 路径")
    ingest_parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
    ingest_parser.add_argument("--limit-matches", type=int, default=None, help="可选：限制 ingest 的比赛数量")
    ingest_parser.set_defaults(func=cmd_ingest)

    run_parser = subparsers.add_parser("run-one", help="对一个已存储或外部传入的 EventPacket 运行编排框架")
    run_parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
    run_parser.add_argument("--source-ref", default=None, help="已存储事件的 source reference")
    run_parser.add_argument("--event-json", default=None, help="EventPacket JSON 文件路径")
    run_parser.set_defaults(func=cmd_run_one)

    eval_parser = subparsers.add_parser("eval", help="对已存储事件运行 smoke 评测")
    eval_parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
    eval_parser.add_argument("--limit", type=int, default=20, help="参与评测的事件数量")
    eval_parser.set_defaults(func=cmd_eval)

    export_parser = subparsers.add_parser("export-training-data", help="从编排框架运行结果导出 SFT 风格训练记录")
    export_parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
    export_parser.add_argument("--output", default="artifacts/training_data.jsonl", help="输出 JSONL 路径")
    export_parser.add_argument("--limit", type=int, default=20, help="导出的记录数量")
    export_parser.set_defaults(func=cmd_export_training_data)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


def cmd_ingest(args: argparse.Namespace) -> None:
    memory = SQLiteMemory(args.db)
    match_count = 0
    event_count = 0
    try:
        for match, events in iter_match_records(args.tar, args.index, max_matches=args.limit_matches):
            memory.upsert_match(match)
            for event in events:
                memory.upsert_event(event)
                event_count += 1
            match_count += 1
        memory.commit()
    finally:
        memory.close()

    _print_json(
        {
            "status": "ok",
            "db": str(Path(args.db)),
            "matches": match_count,
            "events": event_count,
        }
    )


def cmd_run_one(args: argparse.Namespace) -> None:
    memory = SQLiteMemory(args.db)
    try:
        event = _load_event(args, memory)
        if event is None:
            raise SystemExit("没有找到事件。请先运行 ingest，或通过 --event-json 传入 EventPacket。")
        output = CommentaryHarness(memory).run_event(event)
    finally:
        memory.close()
    _print_json(output)


def cmd_eval(args: argparse.Namespace) -> None:
    memory = SQLiteMemory(args.db)
    try:
        events = memory.list_events(limit=args.limit, event_types=DEMO_EVENT_TYPES)
        if not events:
            events = memory.list_events(limit=args.limit)
        harness = CommentaryHarness(memory)
        outputs = [harness.run_event(event) for event in events]
    finally:
        memory.close()

    total = len(outputs)
    verified = sum(1 for item in outputs if item["evaluation"].get("factual"))
    evidence_covered = sum(1 for item in outputs if item["evaluation"].get("evidence_coverage"))
    trace_steps = [step for item in outputs for step in item["trace"]]
    ok_steps = sum(1 for step in trace_steps if step["status"] in {"ok", "fallback"})
    fallback_steps = sum(1 for step in trace_steps if step["status"] == "fallback")
    elapsed = [step["elapsed_ms"] for step in trace_steps]
    baseline_outputs = [_baseline_commentary(event) for event in events]
    baseline_coverage = sum(1 for text in baseline_outputs if text)
    with_game_info = sum(1 for item in outputs if item["evidence"].get("match_info"))
    with_history = sum(1 for item in outputs if item["evidence"].get("timeline_events"))

    _print_json(
        {
            "status": "ok",
            "events": total,
            "baseline_template": {
                "coverage": round(baseline_coverage / total, 4) if total else 0,
                "uses_tool_chain": False,
            },
            "planner_executor_with_game_info": {
                "coverage": round(with_game_info / total, 4) if total else 0,
                "tool_chain": ["Game Search", "Game Info Retrieval"],
            },
            "planner_executor_with_game_info_and_history": {
                "coverage": round(with_history / total, 4) if total else 0,
                "tool_chain": ["Game Search", "Game Info Retrieval", "Match History Retrieval"],
            },
            "planner_executor_full": {
                "factual_pass_rate": round(verified / total, 4) if total else 0,
                "evidence_coverage": round(evidence_covered / total, 4) if total else 0,
                "tool_success_rate": round(ok_steps / len(trace_steps), 4) if trace_steps else 0,
                "fallback_steps": fallback_steps,
                "avg_step_latency_ms": round(sum(elapsed) / len(elapsed), 3) if elapsed else 0,
            },
        }
    )


def cmd_export_training_data(args: argparse.Namespace) -> None:
    memory = SQLiteMemory(args.db)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        events = memory.list_events(limit=args.limit, event_types=DEMO_EVENT_TYPES)
        if not events:
            events = memory.list_events(limit=args.limit)
        harness = CommentaryHarness(memory)
        with output_path.open("w", encoding="utf-8") as handle:
            for event in events:
                output = harness.run_event(event)
                if output["evaluation"].get("risk") == "high":
                    continue
                record = _training_record(event, output)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
    finally:
        memory.close()

    _print_json({"status": "ok", "output": str(output_path), "records": written})


def _load_event(args: argparse.Namespace, memory: SQLiteMemory) -> EventPacket | None:
    if args.event_json:
        with Path(args.event_json).open("r", encoding="utf-8") as handle:
            return EventPacket.from_dict(json.load(handle))
    if args.source_ref:
        return memory.get_event(args.source_ref)
    return memory.first_event(preferred_types=DEMO_EVENT_TYPES)


def _training_record(event: EventPacket, output: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "sft",
        "messages": [
            {
                "role": "system",
                "content": "你是 TinySoccerAgent，一个事件驱动的足球解说智能体编排框架。请生成带证据意识和校验意识的解说。",
            },
            {"role": "user", "content": json.dumps(event.to_dict(), ensure_ascii=False)},
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "commentary": output["commentary"],
                        "known_info": output["known_info"],
                        "tool_chain": output["tool_chain"],
                        "evaluation": output["evaluation"],
                        "trace": [
                            {
                                "agent": step["agent"],
                                "tool": step["tool"],
                                "status": step["status"],
                            }
                            for step in output["trace"]
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "source_refs": event.source_refs,
    }


def _print_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _configure_stdout() -> None:
    # Windows 终端默认编码可能不是 UTF-8，这里强制 stdout 使用 UTF-8，避免中文输出乱码。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _baseline_commentary(event: EventPacket) -> str:
    # eval 里的最小 baseline：不使用 Game Search / Retrieval，只复述当前事件描述。
    minute = f"{event.minute}，" if event.minute else ""
    return f"{minute}{event.raw_description}" if event.raw_description else ""


if __name__ == "__main__":
    raise SystemExit(main())
