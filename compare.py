#!/usr/bin/env python3
"""정렬에 무관하게 두 텍스트 파일의 내용을 비교한다."""

import argparse
import sys
from collections import Counter
from pathlib import Path


def read_lines(path: Path, encoding: str, ignore_empty: bool) -> list[str]:
    with path.open("r", encoding=encoding, errors="replace", newline="") as f:
        lines = [line.rstrip("\r\n") for line in f]
    if ignore_empty:
        lines = [line for line in lines if line.strip() != ""]
    return lines


def compare(lines_a: list[str], lines_b: list[str]) -> tuple[Counter, Counter, int]:
    counter_a = Counter(lines_a)
    counter_b = Counter(lines_b)
    only_a = counter_a - counter_b
    only_b = counter_b - counter_a
    common_count = sum((counter_a & counter_b).values())
    return only_a, only_b, common_count


def format_section(title: str, counter: Counter) -> str:
    if not counter:
        return f"[{title}] 없음\n"
    out = [f"[{title}] {sum(counter.values())} 행"]
    for line, count in counter.most_common():
        if count > 1:
            out.append(f"  (x{count}) {line}")
        else:
            out.append(f"  {line}")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="정렬 차이를 무시하고 두 텍스트 파일을 비교한다."
    )
    parser.add_argument("file_a", type=Path, help="비교할 첫 번째 파일")
    parser.add_argument("file_b", type=Path, help="비교할 두 번째 파일")
    parser.add_argument(
        "--encoding", default="utf-8",
        help="파일 인코딩 (기본: utf-8). 예: cp949, euc-kr",
    )
    parser.add_argument(
        "--keep-empty", action="store_true",
        help="빈 행도 비교 대상에 포함 (기본은 빈 행 무시)",
    )
    args = parser.parse_args()

    for path in (args.file_a, args.file_b):
        if not path.is_file():
            print(f"오류: 파일을 찾을 수 없습니다 - {path}", file=sys.stderr)
            return 2

    ignore_empty = not args.keep_empty
    lines_a = read_lines(args.file_a, args.encoding, ignore_empty)
    lines_b = read_lines(args.file_b, args.encoding, ignore_empty)

    only_a, only_b, common_count = compare(lines_a, lines_b)

    print(f"파일 A: {args.file_a}  ({len(lines_a)} 행)")
    print(f"파일 B: {args.file_b}  ({len(lines_b)} 행)")
    print(f"공통 행: {common_count} 행")
    print()
    print(format_section("A에만 있음", only_a), end="")
    print()
    print(format_section("B에만 있음", only_b), end="")

    identical = not only_a and not only_b
    print()
    print("결과: 두 파일은 정렬을 무시하면 동일합니다." if identical
          else "결과: 두 파일은 차이가 있습니다.")
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
