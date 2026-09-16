#!/bin/bash
# 시간 제한 반복 실행: 100초마다 끊고 재개 (캐시로 이어서)
END=$((SECONDS+100))
cd ~/projects/university/scripts
while [ $SECONDS -lt $END ]; do
  timeout 30 python3 02_fetch_items.py >> /tmp/fetch02.log 2>&1
done
echo "청크 종료. 로그 마지막:"
tail -2 /tmp/fetch02.log
