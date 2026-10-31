# 이음온 로고

발표 자료(PPT)와 인쇄물에 쓰는 로고 원본입니다. `png/` 폴더의 PNG를 바로 슬라이드에 넣으면 됩니다.
SVG는 편집용 원본이며, 글자는 Noto Sans KR 폰트가 설치된 환경에서만 같은 모양으로 보입니다.

## 심볼의 의미

- **두 잎**: 자주색 잎은 어르신의 생활 언어, 청록색 잎은 행정의 정책 언어입니다.
- **겹치는 진보라 부분**: 두 말을 믿을 수 있게 잇는 "이음"입니다.
- **금빛 점**: 따뜻함(온)을 뜻하며, 사람이 두 팔을 벌린 모습으로도 읽힙니다.
- **올리브색 줄기**: 하나의 뿌리에서 자라는 돌봄을 나타냅니다.

## 파일 안내

| 파일 | 용도 |
| --- | --- |
| `iumon-logo-horizontal.png` | 밝은 배경 슬라이드의 상단·하단 로고 (투명 배경) |
| `iumon-logo-horizontal-cream.png` | 크림색 배경이 포함된 가로형 |
| `iumon-logo-horizontal-reverse.png` | 진보라 배경 위 가로형 (표지, 마무리 슬라이드) |
| `iumon-logo-stacked.png` | 가운데 정렬 세로형 (투명 배경) |
| `iumon-logo-stacked-cream.png` / `-reverse.png` | 배경이 포함된 세로형 |
| `iumon-symbol.png` | 심볼만 (투명 배경) |
| `iumon-badge-cream.png` / `iumon-badge-plum.png` | 앱 아이콘 모양의 둥근 사각 배지 |
| `iumon-wordmark.png` | 글자만 (투명 배경) |

## 색상

| 이름 | 값 | 쓰임 |
| --- | --- | --- |
| 크림 | `#FAF8F2` | 배경 |
| 진보라 | `#2F1F4F` | 글자, 잎 겹침 |
| 자주 | `#96266B` | 왼쪽 잎, "온" 강조 |
| 청록 | `#2B7A6F` | 오른쪽 잎 |
| 올리브 | `#8C8A2E` | 줄기 |
| 금빛 | `#D9B452` | 점, 반전형 "온" 강조 |

## 다시 만들기

```
python design/logo/build_logo.py
```

Edge 또는 Chrome이 설치된 Windows에서 SVG를 다시 쓰고 PNG를 3배 해상도로 렌더링합니다.
