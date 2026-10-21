# 이 저장소에서 지킬 것(Codex · 짧게)

같은 실수를 두 번 보면 한 줄씩 더하고, 자꾸 어기면 `scripts/check.sh`로 옮겨요. 쓰는 쪽: 짝 Claude 세션(Personal `builds/medical-data-hands-on`).

- **검사 명령 하나:** 끝내기 전에 `sh scripts/check.sh`를 돌리고, 출력 그대로 답 파일에 붙여요. 하나라도 실패하면 「됐다」고 하지 않아요.
- **`expected/`는 읽기만:** 기대 결과는 Codex 밖에서 짝 세션이 손으로 센 값이에요. 고치거나 다시 만들거나 권한을 풀지 않아요. 숫자가 다르면 기준을 고치지 말고 「기대 결과가 틀린 것 같다」와 까닭을 답에 적어요.
- **원본은 읽기만:** `.local/FHIR-LINE-01/runs/original/fhir/`와 `.local/public-data/`에는 쓰지 않아요. 작업은 이 저장소 안에서만 해요.
- **층 방향:** staging(병원마다 · `staging/hospital_a` …)은 source · seed만, common(공통 표 · M3 요청 07에서 지움)과 omop(OMOP CDM 5.4 표 · M3)은 staging · seed만, intermediate는 common · omop · seed만, marts는 intermediate · common · omop · seed만, reports(L6 요약)는 marts만 읽어요(`python -m fhir_line layers`). staging보다 위에서 `raw_resources`를 읽지 않아요. 병원마다 다른 것(코드 · 날짜 · 방문 종류 · 나이)은 그 병원의 staging과 `code_map`에만 둬요.
- **바뀌면 안 되는 층:** `scripts/check.sh`의 `FROZEN_BASE` 뒤로 `FROZEN_PATHS`(지금 L4 ~ L6)를 고치면 검사가 실패해요. 고쳐야 할 것 같으면 멈추고 까닭을 답에 적어요. 기준 커밋은 짝 Claude 세션이 요청서에서만 바꿔요.
- **정의 번호 · 결정 번호:** 모델 머리 주석과 테스트 이름에 그것이 지키는 정의 번호(D1 ~ D7 · L0 ~ L2)와 결정 번호(`docs/decisions/NNNN` · M3부터)를 적어요.
- **설계 글과 결정 기록은 읽기만:** `docs/design/` · `docs/decisions/`는 짝 Claude 세션이 써요. 코드가 결정과 어긋나야 할 것 같으면 멈추고 까닭을 답에 적어요.
- **답 맨 위 변경 요약 다섯 칸:** 무엇을 · 왜(결정 번호) · 바뀐 파일 수와 층 · 확인한 것 · 남은 것.
- **요청 하나에 한 가지:** 구조 바꾸기(리팩터링)와 동작 바꾸기를 한 요청에 섞지 않아요. 쓰지 않게 된 모델 · 열 · 파일은 지우고 답의 「지운 것」에 적어요(`_old` · 주석으로 남기지 않음).
- **새 패키지는 먼저 묻기:** `requirements.lock`에 없는 것을 받지 않아요. 필요하면 크기와 까닭을 답에 적고 멈춰요.
- **커밋하지 않아요:** 짝 Claude 세션이 확인한 뒤 커밋해요. push · 배포는 하지 않아요.
- **상한:** 요청 하나에 2시간 · 같은 실패를 세 번 넘게 되풀이하면 멈추고 답 파일에 적어요.
