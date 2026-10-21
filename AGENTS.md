# 이 저장소에서 지킬 것(Codex · 짧게)

같은 실수를 두 번 보면 한 줄씩 더하고, 자꾸 어기면 `scripts/check.sh`로 옮겨요. 담당: 의료 Codex(Personal `builds/medical-data-hands-on`). A′의 별도 사전/최종 검수: 방법 감독(`builds-method.codex`).

- **검사 명령 하나:** 끝내기 전에 `sh scripts/check.sh`를 돌리고, 출력 그대로 답 파일에 붙여요. 하나라도 실패하면 「됐다」고 하지 않아요.
- **기존 `expected/` · `answer_key/`는 읽기만:** 앞선 마일스톤에서 별도로 고정한 기대 결과예요. 고치거나 다시 만들거나 파일을 더하거나 권한을 풀지 않아요. 숫자가 다르면 기준을 고치지 말고 「기대 결과가 틀린 것 같다」와 까닭을 답에 적어요.
- **A′ 새 기대값만 별도 작성 허용:** 사용자 승인된 `REQ-medical-a-prime-preserve-all-1021.md`에 따라 의료 담당이 `answer_key_a_prime/`·`expected_a_prime/`를 제품 구현 전에 작성해요. 원천만 읽는 표준 라이브러리 계산과 수기 반례를 사용하고 제품 파서·DB 결과를 기대값 입력으로 쓰지 않아요. 방법 감독의 별도 사전 검수 → 수정 완료 → 해시·읽기 전용 고정 → 제품 구현 순서를 지켜요. 고정 뒤 수정·권한 해제는 하지 않아요.
- **원본은 읽기만:** `.local/FHIR-LINE-01/runs/original/fhir/`와 `.local/public-data/`에는 쓰지 않아요. 작업은 이 저장소 안에서만 해요.
- **층 방향:** staging(병원마다 · `staging/hospital_a` …)은 source · seed만, omop(OMOP CDM 5.4 표 + 옆 표 · M3)은 staging · seed · omop만(결정 0011), intermediate는 omop · seed · intermediate만, marts는 intermediate · omop · seed만, reports(L6 요약)는 marts만 읽어요(`python -m fhir_line layers` · 공통 테이블 common은 M3 요청 07에서 지움).
- **바뀌면 안 되는 층:** `scripts/check.sh`의 `FROZEN_BASE` 뒤로 `FROZEN_PATHS`(지금 L4 ~ L6)를 고치면 검사가 실패해요. `FROZEN_BASE`가 비어 있으면 그 반복은 결정 기록에 따라 계산 층을 바꾸는 중이에요. 지금 고정한 것: L4 ~ L6 + `seeds/indicator_concepts.csv` · `as_of_labels.csv`(M3 요청 07 뒤). 고쳐야 할 것 같으면 멈추고 까닭을 답에 적어요. 기준 커밋은 짝 Claude 세션이 요청서에서만 바꿔요.
- **정의 번호 · 결정 번호:** 모델 머리 주석과 테스트 이름에 그것이 지키는 정의 번호(D1 ~ D7 · L0 ~ L2)와 결정 번호(`docs/decisions/NNNN` · M3부터)를 적어요.
- **설계·결정의 담당:** 의료 담당이 이번 승인 범위의 새 A′ 설계·결정을 `docs/design/`·`docs/decisions/`에 쓰고 방법 감독이 별도 검수해요. 기존 수용한 정의·결정은 유지해요. 코드가 결정과 어긋나야 할 것 같으면 해당 변경을 멈추고 까닭을 답에 적어요.
- **답 맨 위 변경 요약 다섯 칸:** 무엇을 · 왜(결정 번호) · 바뀐 파일 수와 층 · 확인한 것 · 남은 것.
- **요청 하나에 한 가지:** 구조 바꾸기(리팩터링)와 동작 바꾸기를 한 요청에 섞지 않아요. 쓰지 않게 된 모델 · 열 · 파일은 지우고 답의 「지운 것」에 적어요(`_old` · 주석으로 남기지 않음).
- **새 패키지는 먼저 묻기:** `requirements.lock`에 없는 것을 받지 않아요. 필요하면 크기와 까닭을 답에 적고 멈춰요.
- **로컬 커밋만:** 이번 위임은 의료 담당의 자기 제품·작업실 파일 로컬 커밋을 허용해요. 공유 index가 빈지 먼저 확인하고 정확한 경로만 stage해요. 다른 담당의 변경은 보존하고 push · 배포는 하지 않아요.
- **상한:** 요청 하나에 2시간 · 같은 실패를 세 번 넘게 되풀이하면 멈추고 답 파일에 적어요.
