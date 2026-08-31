# Steam 큐레이터 자동 동기화

> 현재 상태: **활성화** — GitHub Actions가 6시간마다 Steam 큐레이터 평가를 확인합니다.

이 폴더는 GitHub 저장소 `http-etashi`의 루트로 사용합니다. `.github/workflows/sync-steam-reviews.yml`이 6시간마다 큐레이터 평가를 확인합니다.

- 새 평가나 수정된 평가가 있으면 목록 파일과 사이트의 내장 데이터를 갱신합니다.
- 변경 사항이 없으면 커밋하지 않습니다.
- GitHub의 **Actions → Sync Steam curator reviews → Run workflow**에서 즉시 수동 실행할 수도 있습니다.
- 저장소의 Actions 권한에서 쓰기가 막힌 경우 **Settings → Actions → General → Workflow permissions → Read and write permissions**를 선택해야 합니다.

한글화 앱의 GitHub 목록은 앱을 열 때 GitHub 공개 저장소를 직접 확인합니다. 새 공개 저장소가 생기면 별도 목록 편집 없이 제목, 설명, 미리보기와 함께 자동 추가됩니다.
