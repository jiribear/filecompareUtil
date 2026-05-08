#!/usr/bin/env python3
"""정렬에 무관하게 두 텍스트 파일의 내용을 비교 (대용량 지원).

외부 정렬(External Merge Sort) + 스트리밍 머지 비교 방식이라
파일 크기가 수 GB여도 메모리는 청크 한도(--chunk-mb, 기본 256MB)로 고정된다.
"""

import argparse
import heapq
import sys
import tempfile
import time
from contextlib import ExitStack
from itertools import groupby
from pathlib import Path
from typing import Iterator, Optional


def _progress(msg: str) -> None:
    print(f"      {msg}", file=sys.stderr, flush=True)


def iter_lines(path: Path, encoding: str, ignore_empty: bool) -> Iterator[str]:
    with path.open("r", encoding=encoding, errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if ignore_empty and not line.strip():
                continue
            yield line


def _flush_chunk(buffer: list[str], tmp_dir: Path, label: str, idx: int) -> Path:
    buffer.sort()
    path = tmp_dir / f"{label}_{idx:05d}.chunk"
    with path.open("w", encoding="utf-8", newline="") as f:
        for line in buffer:
            f.write(line)
            f.write("\n")
    return path


def sort_to_chunks(
    lines: Iterator[str],
    tmp_dir: Path,
    chunk_bytes: int,
    label: str,
    phase_start: Optional[float] = None,
    report_every: int = 1_000_000,
) -> tuple[list[Path], int]:
    chunks: list[Path] = []
    buffer: list[str] = []
    buffer_bytes = 0
    total = 0
    bytes_read = 0
    start = phase_start if phase_start is not None else time.monotonic()
    for line in lines:
        buffer.append(line)
        line_cost = 60 + len(line)
        buffer_bytes += line_cost
        bytes_read += len(line) + 1
        total += 1
        if total % report_every == 0:
            elapsed = time.monotonic() - start
            _progress(
                f"{label}: {total:,} 행 처리, 청크 {len(chunks)}개 spill, "
                f"{bytes_read / (1024 * 1024):.1f} MB 읽음, 경과 {elapsed:.1f}s"
            )
        if buffer_bytes >= chunk_bytes:
            chunks.append(_flush_chunk(buffer, tmp_dir, label, len(chunks)))
            elapsed = time.monotonic() - start
            _progress(
                f"{label}: 청크 {len(chunks)} spill "
                f"({bytes_read / (1024 * 1024):.1f} MB까지, 경과 {elapsed:.1f}s)"
            )
            buffer = []
            buffer_bytes = 0
    if buffer:
        chunks.append(_flush_chunk(buffer, tmp_dir, label, len(chunks)))
    return chunks, total


def merge_chunks(chunks: list[Path]) -> Iterator[str]:
    with ExitStack() as stack:
        files = [stack.enter_context(p.open("r", encoding="utf-8")) for p in chunks]
        iters = [(line.rstrip("\n") for line in f) for f in files]
        yield from heapq.merge(*iters)


def grouped(it: Iterator[str]) -> Iterator[tuple[str, int]]:
    for line, group in groupby(it):
        yield line, sum(1 for _ in group)


def diff_streams(
    runs_a: Iterator[tuple[str, int]],
    runs_b: Iterator[tuple[str, int]],
) -> Iterator[tuple[str, str, int]]:
    ra = next(runs_a, None)
    rb = next(runs_b, None)
    while ra is not None and rb is not None:
        la, ca = ra
        lb, cb = rb
        if la == lb:
            common = min(ca, cb)
            if common:
                yield ("common", la, common)
            if ca > cb:
                yield ("only_a", la, ca - cb)
            elif cb > ca:
                yield ("only_b", lb, cb - ca)
            ra = next(runs_a, None)
            rb = next(runs_b, None)
        elif la < lb:
            yield ("only_a", la, ca)
            ra = next(runs_a, None)
        else:
            yield ("only_b", lb, cb)
            rb = next(runs_b, None)
    while ra is not None:
        la, ca = ra
        yield ("only_a", la, ca)
        ra = next(runs_a, None)
    while rb is not None:
        lb, cb = rb
        yield ("only_b", lb, cb)
        rb = next(runs_b, None)


def _write_diff(out: Optional["object"], line: str, count: int) -> None:
    if out is None:
        return
    for _ in range(count):
        out.write(line)
        out.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="정렬을 무시하고 두 텍스트 파일을 비교 (외부 정렬 + 머지, 대용량 지원)."
    )
    parser.add_argument("file_a", type=Path, help="비교할 첫 번째 파일")
    parser.add_argument("file_b", type=Path, help="비교할 두 번째 파일")
    parser.add_argument("--encoding", default="utf-8",
                        help="파일 인코딩 (기본: utf-8). 예: cp949, euc-kr")
    parser.add_argument("--keep-empty", action="store_true",
                        help="빈 행도 비교 대상에 포함 (기본은 빈 행 무시)")
    parser.add_argument("--chunk-mb", type=int, default=256,
                        help="외부 정렬 청크 메모리 한도(MB, 기본 256)")
    parser.add_argument("--tmp-dir", type=Path, default=None,
                        help="임시 정렬 파일 디렉토리 (기본: 시스템 임시 폴더)")
    parser.add_argument("--out-only-a", type=Path, default=None,
                        help="A에만 있는 행 전체를 기록할 파일")
    parser.add_argument("--out-only-b", type=Path, default=None,
                        help="B에만 있는 행 전체를 기록할 파일")
    parser.add_argument("--preview", type=int, default=20,
                        help="콘솔 미리보기 행 수 (기본 20, 0이면 미리보기 없음)")
    args = parser.parse_args()

    for p in (args.file_a, args.file_b):
        if not p.is_file():
            print(f"오류: 파일을 찾을 수 없습니다 - {p}", file=sys.stderr)
            return 2

    chunk_bytes = max(1, args.chunk_mb) * 1024 * 1024
    ignore_empty = not args.keep_empty

    tmp_parent = str(args.tmp_dir) if args.tmp_dir else None
    if tmp_parent:
        Path(tmp_parent).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="filecmp_", dir=tmp_parent) as tmp:
        tmp_path = Path(tmp)

        print(f"[1/3] 외부 정렬: A = {args.file_a}", file=sys.stderr, flush=True)
        phase_start = time.monotonic()
        chunks_a, total_a = sort_to_chunks(
            iter_lines(args.file_a, args.encoding, ignore_empty),
            tmp_path, chunk_bytes, "A",
            phase_start=phase_start,
        )
        elapsed_a = time.monotonic() - phase_start
        _progress(
            f"A 완료: 청크 {len(chunks_a)}개, {total_a:,} 행, 경과 {elapsed_a:.1f}s"
        )

        print(f"[2/3] 외부 정렬: B = {args.file_b}", file=sys.stderr, flush=True)
        phase_start = time.monotonic()
        chunks_b, total_b = sort_to_chunks(
            iter_lines(args.file_b, args.encoding, ignore_empty),
            tmp_path, chunk_bytes, "B",
            phase_start=phase_start,
        )
        elapsed_b = time.monotonic() - phase_start
        _progress(
            f"B 완료: 청크 {len(chunks_b)}개, {total_b:,} 행, 경과 {elapsed_b:.1f}s"
        )

        print("[3/3] 머지 비교 중...", file=sys.stderr, flush=True)
        phase_start = time.monotonic()

        common_count = 0
        only_a_count = 0
        only_b_count = 0
        only_a_unique = 0
        only_b_unique = 0
        preview_a: list[tuple[str, int]] = []
        preview_b: list[tuple[str, int]] = []

        with ExitStack() as stack:
            fa = (stack.enter_context(args.out_only_a.open("w", encoding="utf-8"))
                  if args.out_only_a else None)
            fb = (stack.enter_context(args.out_only_b.open("w", encoding="utf-8"))
                  if args.out_only_b else None)

            runs_a = grouped(merge_chunks(chunks_a))
            runs_b = grouped(merge_chunks(chunks_b))

            merge_report_every = 1_000_000
            next_report = merge_report_every
            for kind, line, count in diff_streams(runs_a, runs_b):
                if kind == "common":
                    common_count += count
                elif kind == "only_a":
                    only_a_count += count
                    only_a_unique += 1
                    _write_diff(fa, line, count)
                    if len(preview_a) < args.preview:
                        preview_a.append((line, count))
                else:
                    only_b_count += count
                    only_b_unique += 1
                    _write_diff(fb, line, count)
                    if len(preview_b) < args.preview:
                        preview_b.append((line, count))
                processed = common_count + only_a_count + only_b_count
                if processed >= next_report:
                    elapsed = time.monotonic() - phase_start
                    _progress(
                        f"머지 진행: {processed:,} 행 비교, 경과 {elapsed:.1f}s"
                    )
                    next_report = processed - (processed % merge_report_every) + merge_report_every

        elapsed_merge = time.monotonic() - phase_start
        _progress(f"머지 완료: 경과 {elapsed_merge:.1f}s")

    print()
    print(f"파일 A: {args.file_a}  ({total_a:,} 행)")
    print(f"파일 B: {args.file_b}  ({total_b:,} 행)")
    print(f"공통 행: {common_count:,} 행")
    print(f"A에만 있음: {only_a_count:,} 행 (유니크 {only_a_unique:,})")
    print(f"B에만 있음: {only_b_count:,} 행 (유니크 {only_b_unique:,})")

    if args.preview > 0 and preview_a:
        print()
        print(f"[A에만 있음 미리보기 (최대 {args.preview})]")
        for line, count in preview_a:
            prefix = f"  (x{count}) " if count > 1 else "  "
            print(f"{prefix}{line}")
    if args.preview > 0 and preview_b:
        print()
        print(f"[B에만 있음 미리보기 (최대 {args.preview})]")
        for line, count in preview_b:
            prefix = f"  (x{count}) " if count > 1 else "  "
            print(f"{prefix}{line}")

    identical = only_a_count == 0 and only_b_count == 0
    print()
    print("결과: 두 파일은 정렬을 무시하면 동일합니다." if identical
          else "결과: 두 파일은 차이가 있습니다.")
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
