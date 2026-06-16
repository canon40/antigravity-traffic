========================================
  blog auto.exe 빌드 방법 (배포용)
========================================

1. 준비
   - Python 가상환경(.venv) 활성화
   - pip install pyinstaller

2. 빌드 실행
   - build_blog_auto.bat 더블클릭 또는
   - 명령 프롬프트에서: build_blog_auto.bat

3. 동작
   - config.py 를 config_dist.py 내용으로 잠시 덮어쓴 뒤
     (API 키·계정 정보 제거된 상태로)
   - PyInstaller로 "blog auto.exe" 생성
   - 빌드 후 config.py 를 원래대로 복원

4. 결과물
   - dist\blog auto.exe
   - 이 파일만 다른 PC에 복사해 사용 가능
   - 해당 PC에서 첫 실행 시 지침 탭에는 "사용 설명서"(API 발급 방법, 글쓰기 방법)가 기본으로 들어 있음
   - 설정 탭에서 API 키·계정 입력 후 "설정 저장 및 연동" 하면 accounts.json 에 저장됨

5. 주의
   - 빌드 전 본인용 config.py 에 있는 API 키·비밀번호는 exe 에 포함되지 않음 (config_dist 로 교체되어 빌드됨)
   - 배포용으로 쓸 exe 만 만들 때만 build_blog_auto.bat 사용
