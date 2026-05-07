# filecompareUtil

정렬 순서가 달라도 두 텍스트 파일(.txt, .inf 등)의 내용이 같으면 동일하다고
판정하는 CLI 도구.

## 동작 방식

- 두 파일을 행 단위로 읽어 multiset(개수가 있는 집합)으로 비교
- 같은 행이 A의 1번째, B의 2번째에 있어도 동일한 것으로 처리
- 같은 행이 여러 번 등장하면 양쪽의 등장 횟수까지 같아야 동일로 판정
- 빈 행은 기본적으로 무시 (`--keep-empty`로 비활성화 가능)

## 사용법

```bash
python3 compare.py <파일A> <파일B> [--encoding utf-8] [--keep-empty]
```

### 예시

```bash
python3 compare.py samples/a.txt samples/b.txt
python3 compare.py a.inf b.inf --encoding cp949
```

### 종료 코드

- `0` : 두 파일이 (정렬 무시) 동일
- `1` : 차이가 있음
- `2` : 입력 파일을 찾을 수 없음

## 출력

- 파일별 행 개수, 공통 행 개수
- A에만 있는 행 목록 (중복 시 `(x개수)` 표시)
- B에만 있는 행 목록 (중복 시 `(x개수)` 표시)
