# MP4 Cutter

MP4 영상의 원하는 구간만 **무손실로** 빠르게 잘라내는 심플한 프로그램입니다.
재인코딩을 하지 않기 때문에 화질이 그대로이고, 잘라낸 길이만큼만 용량이 됩니다.
(Clipchamp 같은 편집기처럼 파일이 커지지 않습니다.)

![screenshot](screenshot.png)

## 기능

- 영상 열기 → 타임라인 클릭으로 위치 이동, 해당 장면 미리보기
- 시작(I) / 끝(O) 지정 → 저장
- 여러 구간 추가 → **하나로 이어 붙이기**(중간 잘라내기) 또는 **각각 따로 저장**
- 저장 방식
  - **무손실 빠른 자르기** (기본): 몇 초 안에 끝남, 화질·용량 원본 그대로. 시작 지점이 가장 가까운 키프레임에 맞춰지므로 1~2초 정도 앞에서 시작할 수 있음
  - **정확한 자르기**: 프레임 단위로 정확, H.264로 다시 인코딩 (CRF 20, 조금 느림)
- exe 아이콘 위에 영상 파일을 끌어다 놓으면 바로 열림

## 단축키

| 키 | 동작 |
|---|---|
| ← / → | 1초 이동 |
| Shift + ← / → | 1프레임 이동 |
| PgUp / PgDn | 10초 이동 |
| Home / End | 처음 / 끝 |
| I / O | 현재 위치를 시작 / 끝으로 |
| A | 구간 추가 |
| Ctrl+O / Ctrl+S | 열기 / 저장 |

## 다운로드 (Windows)

[Releases](../../releases) 에서 `MP4Cutter.exe` 를 받아 실행하면 됩니다. (ffmpeg 포함, 설치 불필요)

> 처음 실행 시 Windows SmartScreen 경고가 나오면 "추가 정보 → 실행"을 누르세요. (서명되지 않은 개인 프로그램이라 나오는 경고입니다)

## Python으로 실행 (Windows / Mac / Linux)

```bash
pip install -r requirements.txt
python mp4cutter.py
```

Windows에서는 `run.bat` 더블클릭으로도 실행됩니다.

## exe 빌드

GitHub에 올리면 `.github/workflows/build.yml` 이 자동으로 Windows exe를 만듭니다.

- **Actions 탭** → 최신 실행 → 아래 Artifacts 에서 `MP4Cutter-windows` 다운로드
- 또는 **Releases → Draft a new release** 로 태그(예: `v1.0.0`)를 만들어 발행하면 exe가 Release에 자동 첨부됩니다.

직접 빌드하려면:

```bash
pip install -r requirements.txt pyinstaller
python -c "import imageio_ffmpeg, shutil; shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), 'ffmpeg.exe')"
pyinstaller --onefile --windowed --name MP4Cutter --add-binary "ffmpeg.exe;." mp4cutter.py
```

## 라이선스

MIT. Windows 빌드에는 ffmpeg(GPL)가 포함됩니다.
