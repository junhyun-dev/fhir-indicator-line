# A′ 기대값 계산·검사

D1~D7 · 결정 0004~0011·0013. 의료 담당이 제품 구현 전에 작성하고 방법 감독이 별도 검수한다. 기존 `answer_key/`·`expected/`와 독립된 새 경로다. 계산기는 원천 FHIR와 명시한 정의만 읽으며 제품 모듈·DB·기존 기대 CSV는 입력으로 사용하지 않는다.

R01 보완의 새 기준은 코드와 체계를 함께 구분한다. 진단 `http://snomed.info/sct` + `59621000`, panel/성분 `http://loinc.org` + 해당 LOINC, 단위 `http://unitsofmeasure.org` + `mm[Hg]`, 방문 `http://terminology.hl7.org/CodeSystem/v3-ActCode` + 승인된 class만 해석한다. URI 생략·축약·별칭은 자동 보정하지 않는다. `mmHg`는 원래 표시값으로 보존하며 이 새 기준에서 단위 code의 추가 매핑으로 받지 않는다. 기존 A/B 제품과 그 alias 매핑은 변경하지 않는다.

다른 namespace의 같은 문자열도 원천 사실에서 지우지 않는다. 미대응 진단은 고혈압 이관/대상 판정에 쓰지 않고, 방문·혈압 성분·단위의 미대응 개념은 0으로 남겨 새 임상 의미를 부여하지 않는다. 모든 원래 panel coding의 code/system 쌍을 JSON 문자열로 보존하고, 첫 후보의 panel_code/panel_system도 component projection에 포함한다. 현재 계약은 `a-prime-preserve-all-3`이며, R01의 v2와 임상 CSV 3개·projection 해시는 같다. v3는 원래 의미와 KCD 후보의 상태를 분리한다.

사전 검수 준비 명령:

```sh
nice -n 10 python3 -B answer_key_a_prime/calculate.py \
  --source .local/FHIR-LINE-01/runs/original/fhir \
  --output expected_a_prime
python3 -B -m unittest discover -s answer_key_a_prime -p 'test_*.py' -v
```

계산기는 기존 출력 덮어쓰기를 거부한다. 검토 수정 뒤 다시 계산해야 한다면 이전 결과를 Git 밖 검토 근거로 보존한 뒤, **고정 전**의 새 출력만 생성한다. 고정 뒤에는 수정·재생성·권한 해제를 하지 않는다.

`omop_facts.csv`는 원래 A의 승인된 임상 의미로 계산한 비교 기준이다. 진단의 320128은 SNOMED `59621000`의 기준이며 **KCD `I109`의 공식 매핑을 증명하지 않는다**. manifest의 `mapping.clinical_basis`는 기존0009의 원래 코드/체계·대응 개념을, `mapping.kcd_candidate`는 후보 주석과 미확인 상태를 담는다. 후보의 product_mapping_gate=blocked·kcd_to_omop=unverified는 유지하며 목표 개념은NULL이다. KCD 후보값으로 원래 코드를 보충하지 않는다.

검사기는 비교 경로를 명시하게 한다. `preserved_source_clinical`의 ok는 원래 승인된 SNOMED basis·후보의 정직한 미확인 상태·CSV/projection 일치에 한정된다. KCD를unverified로 유지한 채 이 임상 보존 비교는 통과할 수 있고, `kcd_route_ok`는false다. `kcd_to_omop` 경로는 현재 항상 실패한다. 후보 상태만verified/approved로 조작하거나 후보를 원래 code/system 대신 쓰면 임상 경로도 통과하지 않는다. 앞서 모든 성공에 KCD verified를 요구한 검사 조건은 이 경로 구분으로 대체했다.

이 조건의 수기 단위 시험 성공은 제품 구현 수용이나 KCD 연동 완료가 아니다. CLI는 비교 전에 고정된 해시/쓰기 권한을 확인하므로 **아직 미고정인 현재 자료로 CLI 성공을 주장하지 않는다**. 감독의 정확한 해시 사전 검수→수정 완료→고정→원래 임상 경로 제품 구현 순서다. 제품 후보 경계와 입력의 original_code/system·별도 candidate 열은 [설계03](../docs/design/03-a-prime-preserve-all.md)에 있다.

실제 결과 비교 명령은 구현 뒤 아래 형태다. `actual/`은 새 출처를 거쳐 추출한 CSV이며, 원본 FHIR에서 답을 복사해 실제 결과로 삼지 않는다.

```sh
python3 -B answer_key_a_prime/check.py \
  --route preserved_source_clinical \
  --expected expected_a_prime --actual .local/FHIR-LINE-A-PRIME/actual \
  --source-facts .local/FHIR-LINE-A-PRIME/actual/source_facts.jsonl
```

CSV 숫자·날짜 형식/키/값은 새 검사기가 확인한다. SQL 테이블의 실제 자료형은 기존 확인 사다리와 구현 단계의 실제 추출 경로에서 확인한다. CSV만으로 원래 SQL 자료형을 증명했다고 하지 않는다. 원천 projection은 선택한 날짜 원문·코드/system·정확한 수치/단위/status 등의 행 해시를 비교한다. 환자/기관 이름과 FHIR 원문은 로그로 출력하지 않는다.

기대 파일과 같은 파일·symlink·hardlink를 실제 결과로 지정하면 거부한다. projection/manifest의 중복 JSON 필드도 마지막 값으로 덮어 읽지 않고 거부한다. 별도 파일에 기대값을 복사한 경우까지 데이터만으로 판별할 수 있다는 뜻은 아니며, 실제 추출 경로의 독립성은 제품 코드·별도 검수로 확인한다.

현재는 사전 검수 전이므로 기대값·코드·manifest를 수정 가능 상태로 준비한다. 별도 검수에서 수정을 닫은 뒤 저장소 루트 기준 `expected_a_prime/SHA256SUMS`에 새 기대 파일과 이 디렉터리의 계산·검사·시험·설명을 포함하고 파일/디렉터리를 읽기 전용으로 고정한다. 기존 해시 목록은 바꾸지 않는다.
