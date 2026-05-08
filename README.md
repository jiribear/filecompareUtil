# filecompareUtil

정렬 순서가 달라도 두 텍스트 파일(.txt, .inf 등)의 내용이 같으면 동일하다고
판정하는 CLI 도구. **외부 정렬 + 스트리밍 머지** 방식이라 수 GB 규모도
메모리 한도 내에서 처리한다.

## 동작 방식

1. 두 파일을 행 단위로 읽으며 청크(기본 256MB) 단위로 메모리 정렬 → 임시 파일로 spill
2. 청크들을 `heapq.merge`로 스트리밍 머지하여 정렬된 행 시퀀스를 만든다
3. 두 정렬 스트림을 머지 비교하며 공통/A전용/B전용 카운트
4. 같은 행이 여러 번 등장하면 양쪽의 등장 횟수까지 같아야 동일로 판정
5. 빈 행은 기본적으로 무시 (`--keep-empty`로 비활성화 가능)

메모리 사용량은 파일 크기가 아니라 `--chunk-mb` 한도에 비례하므로,
4~5GB 파일도 안전하게 비교할 수 있다.

## 사용법

```bash
python3 compare.py <파일A> <파일B> [옵션]
```

### 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--encoding` | `utf-8` | 입력 파일 인코딩 (예: `cp949`, `euc-kr`) |
| `--keep-empty` | off | 빈 행도 비교 대상에 포함 |
| `--chunk-mb` | `256` | 외부 정렬 청크 메모리 한도(MB) |
| `--tmp-dir` | 시스템 임시 | 임시 정렬 파일 디렉토리 |
| `--out-only-a PATH` | 없음 | A에만 있는 행 전체를 파일로 저장 |
| `--out-only-b PATH` | 없음 | B에만 있는 행 전체를 파일로 저장 |
| `--preview N` | `20` | 콘솔 미리보기 행 수 (0이면 미출력) |

### 예시

```bash
# 일반 비교
python3 compare.py samples/a.txt samples/b.txt

# cp949 + 차이 행을 별도 파일로 저장
python3 compare.py a.inf b.inf \
    --encoding cp949 \
    --out-only-a only_a.txt \
    --out-only-b only_b.txt

# 메모리가 빡빡한 환경 (청크 한도 64MB)
python3 compare.py big_a.txt big_b.txt --chunk-mb 64

# 임시 폴더 위치 지정 (대용량 시 디스크 공간이 큰 경로 권장)
python3 compare.py big_a.txt big_b.txt --tmp-dir /data/tmp
```

### 종료 코드

- `0` : 두 파일이 (정렬 무시) 동일
- `1` : 차이가 있음
- `2` : 입력 파일을 찾을 수 없음

## 성능 특성

- 시간 복잡도: O(N log N) (외부 정렬), 실측은 I/O 바운드
- 공간 복잡도: 메모리 ≈ `chunk_mb`, 디스크 임시 ≈ 입력 합계
- 참고 벤치: 216MB × 2 파일 (각 4M 행), `--chunk-mb 64` → 약 14.8초, 최대 RSS 90MB
- 5GB × 2 추정: 약 10~15분, 메모리는 그대로 유지

## 진행 메시지

진행 상황은 stderr로 출력된다(통계는 stdout). 파이프라인에서
통계만 활용하고 싶다면 `2>/dev/null` 처리하면 된다.
