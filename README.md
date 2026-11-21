# SatelliteMap

v4로 보정한 전 세계 육지·물 지도와 두 지도를 합친 PNG를 내려받는 정적 사이트입니다.

사이트: https://ibcytb.github.io/SatelliteMap/

PNG 모음: https://github.com/Ibcytb/SatelliteMap/releases/tag/png-v4

사이트에서 육지·물·둘 다와 크기를 선택하면 미리 생성된 PNG 한 장을 받습니다. `둘 다`는 육지와 바다가 합쳐진 지도이며 두 개의 별도 파일이 아닙니다. 미리보기와 다운로드 선택은 항상 함께 바뀝니다. `기본`과 `1,000px 단위` 탭을 이용하거나, `전체 크기`를 펼쳐 세 종류의 PNG를 검색하고 저장할 수 있습니다.

## 준비하는 크기

- 512, **1024, 1536, 2048, 3072, 4096, 6144, 8192, 12288, 16384, 24576, 32768, 49152, 65536**
- **1000, 2000, 3000, …, 64000** — 1000px 간격의 모든 크기
- 중복 없는 78개 크기 × 육지/물/합성 = 총 234개 PNG

모든 PNG는 표시된 크기와 같은 가로·세로 해상도를 갖습니다. 육지와 물은 투명 RGBA이고, 합성 지도는 두 마스크가 덮는 원래 색상을 보존한 RGB PNG입니다. 물 지도에는 바다와 내륙 수역이 포함됩니다. 다운로드할 때 브라우저에서 변환하거나 대형 캔버스를 만들지 않습니다. 각 파일의 정확한 용량과 SHA-256은 `docs/catalog.json`에 있습니다.

## 배포 구조

GitHub Pages는 `docs/`의 HTML/CSS/JavaScript와 미리보기만 서비스합니다. 큰 PNG는 `png-v4` GitHub Release의 첨부 파일로 제공합니다. 각 파일은 GitHub Release의 2GiB 제한을 검사합니다. 원본 TIFF는 생성 작업에서 사용하는 비공개 초안 `source-v4` Release에 보관합니다. 생성한 대형 PNG와 TIFF는 Git 이력에 넣지 않습니다.

Actions의 **Build PNG library**를 실행하면 이미 올라간 PNG를 건너뛰고, 나머지를 병렬 생성합니다. 전체 크기가 준비되고 SHA-256과 크기 정보가 확인된 뒤 목록을 갱신하고 PNG Release와 Pages를 게시합니다. `catalog.json`은 파일 크기, SHA-256 및 다운로드 주소를 포함합니다.

64,000px와 65,536px 합성 PNG를 재생성할 때는 **Optimize large combined PNGs**로 Zopfli 무손실 압축을 분산 처리합니다. 고정 필터만으로 용량 제한을 넘으면 임시 Release ID를 **Optimize combined PNG filters**에 입력합니다. 이 작업은 일곱 가지 PNG 필터를 비교하고 기존 조각보다 작은 결과만 채택하여 하나의 표준 PNG로 결합합니다. 해상도와 RGB 값은 바꾸지 않습니다. 임시 조각은 비공개 초안 Release에만 보관하고 최종 PNG 두 장의 검증과 게시가 성공한 뒤 제거합니다. 이후 **Build PNG library**로 나머지 파일과 목록을 검증합니다. `max_size`를 낮추면 작은 크기만 생성하며 불완전한 목록은 게시하지 않습니다.

## 보정본

최대 크기는 65,536 × 65,536이며 v4 분리를 그대로 사용합니다. 작은 크기는 최근접 이웃 방식으로 축소하고 TIFF의 기존 축소 개요도 사용합니다. 축소 시 작은 섬은 생략될 수 있습니다. 합성 파일은 메모리 사용량을 제한한 행 단위 처리로 생성하고, 모든 PNG 청크의 CRC와 전체 압축 스트림 및 해상도를 검사합니다.

## 배포 검증

`python tools/verify_downloads.py`로 공개 다운로드 주소의 PNG 헤더, 실제 해상도, 색상 모드, 파일 용량을 검사할 수 있습니다. 기존 개별 지도의 원본 대조 결과도 보존합니다.

회귀 검사: `node --test tools/test_catalog.cjs`, `python -m unittest discover -s tools -p "test_*.py"` (후자는 Pillow 필요).

확인 결과: [234개 다운로드 링크 검사](tools/download_validation.json), [합성 PNG 픽셀 대조](tools/combined_pixel_validation.json), [실제 브라우저 다운로드](tools/browser_download_validation.json), [공개 64K PNG 원본 대조](tools/remote_validation.json), [전체 SHA-256 목록](docs/SHA256SUMS.txt).

지도 영상: 사용자 제공 Bing 위성 지도. 영상에 대한 권리는 원 권리자에게 있으며, 이 저장소의 코드는 지도 영상의 사용 권한을 추가로 부여하지 않습니다.
