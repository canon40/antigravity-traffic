# JARVIS 서브모듈 (선택)

Traffic 허브는 `data/programs_catalog.json`에 JARVIS·Traffic bat 목록이 Git에 포함됩니다.  
로컬에서 **실행**하려면 JARVIS 저장소가 필요합니다.

## 권장: Git submodule

```bash
cd "d:\@code\anty traffic"
git submodule add https://github.com/FatihMakes/Mark-XXXIX.git javis
git submodule update --init --recursive
```

클론 후:

```bash
git clone --recurse-submodules https://github.com/canon40/antigravity-traffic.git
```

## 이미 `D:\@code\javis`가 있는 경우

환경변수 없이도 `JARVIS_ROOT` 기본 경로를 사용합니다.  
또는 `javis` 폴더에 junction:

```powershell
mklink /J "d:\@code\anty traffic\javis" "D:\@code\javis"
```

## 카탈로그 갱신

JARVIS에 bat이 추가되면:

```bash
python scripts/sync_javis_catalog.py
git add data/programs_catalog.json
```
