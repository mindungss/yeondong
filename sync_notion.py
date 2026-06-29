name: Notion → JSON 자동 동기화

# ─────────────────────────────────────────────
# 트리거 설정
# ─────────────────────────────────────────────
on:
  schedule:
    # 매일 KST 오전 10:30 = UTC 01:30
    - cron: "0 1 * * *"

  # 수동 실행 (GitHub Actions 탭에서 직접 실행 가능)
  workflow_dispatch:
    inputs:
      force_commit:
        description: "변경 없어도 강제 커밋 (true/false)"
        required: false
        default: "false"

# ─────────────────────────────────────────────
# 권한 설정 (레포 쓰기 권한)
# ─────────────────────────────────────────────
permissions:
  contents: write

jobs:
  sync:
    name: Notion 데이터 동기화
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      # 1. 소스 체크아웃
      - name: 📥 레포지토리 체크아웃
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      # 2. Python 환경 설정
      - name: 🐍 Python 3.11 설정
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      # 3. 의존성 설치
      - name: 📦 패키지 설치
        run: |
          pip install --upgrade pip
          pip install notion-client==2.2.1

      # 4. 동기화 스크립트 실행
      - name: 🔄 Notion → JSON 동기화 실행
        id: sync
        env:
          NOTION_TOKEN:    ${{ secrets.NOTION_TOKEN }}
          NOTION_DB_TREND: ${{ secrets.NOTION_DB_TREND }}
          NOTION_DB_IDEA:  ${{ secrets.NOTION_DB_IDEA }}
          NOTION_DB_RFP:   ${{ secrets.NOTION_DB_RFP }}
          NOTION_DB_NTIS:  ${{ secrets.NOTION_DB_NTIS }}
        run: |
          python sync_notion.py
          echo "스크립트 실행 완료 (exit: $?)"

      # 5. 실제 파일 변경 여부 확인 (수정 + 신규 파일 모두 감지)
      - name: 🔍 JSON 파일 변경 여부 확인
        id: check_changes
        run: |
          MODIFIED=$(git diff --name-only data/ 2>/dev/null)
          UNTRACKED=$(git ls-files --others --exclude-standard data/ 2>/dev/null)
          if [ -n "$MODIFIED" ] || [ -n "$UNTRACKED" ]; then
            echo "changed=true" >> $GITHUB_OUTPUT
            echo "변경/신규 파일: $MODIFIED $UNTRACKED"
          else
            echo "changed=false" >> $GITHUB_OUTPUT
            echo "변경된 파일 없음"
          fi

      # 6. 변경이 있을 때만 커밋 & 푸시
      - name: 📤 변경사항 커밋 & 푸시
        if: |
          steps.check_changes.outputs.changed == 'true' ||
          github.event.inputs.force_commit == 'true'
        run: |
          # Git 사용자 설정
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          # 변경된 data/ 파일만 스테이징
          git add data/*.json

          # 커밋 메시지에 KST 시각 포함
          KST_TIME=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
          git commit -m "🔄 자동 데이터 동기화: ${KST_TIME}"

          # 푸시 (충돌 방지를 위해 rebase)
          git pull --rebase origin main
          git push origin main

          echo "✅ 커밋 및 푸시 완료"

      # 7. 변경 없음 → 정상 종료
      - name: ✅ 변경 없음 — 정상 종료
        if: |
          steps.check_changes.outputs.changed == 'false' &&
          github.event.inputs.force_commit != 'true'
        run: |
          KST_TIME=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
          echo "📭 ${KST_TIME} — 노션에 새 데이터 없음. 기존 JSON 유지. 정상 종료."
          exit 0
