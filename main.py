import requests
import json
import os
import traceback
from datetime import datetime, timedelta

SERVICE_KEY = os.environ.get('AIRPORT_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_URL')
DATA_FILE = 'sent_data_final.json'

def send_slack(msg):
    try:
        if SLACK_WEBHOOK_URL:
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        else:
            print("슬랙 URL이 설정되지 않았습니다.")
    except Exception as e:
        print(f"슬랙 전송 에러: {e}")

def get_flight_data(io_type):
    url = "http://openapi.airport.co.kr/service/rest/FlightStatusList/getFlightStatusList"
    params = {
        'serviceKey': SERVICE_KEY,
        'schLineType': 'D',
        'schIOType': io_type,
        'schAirCode': 'CJU',
        'schStTime': '0600',
        'schEdTime': '2359',
        'numOfRows': '500',
        '_type': 'json'
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        items = data['response']['body']['items']['item']
        return [items] if isinstance(items, dict) else items
    except Exception as e:
        # API 오류 시 빈 리스트 반환
        return []

def check_jeju():
    print("=== 봇 실행 시작 ===")
    
    if not SERVICE_KEY or not SLACK_WEBHOOK_URL:
        print("에러: API Key 또는 Slack URL이 없습니다.")
        return

    # 1. 장부 파일 로드 (에러 방지 처리)
    sent_ids = set()
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content: # 파일이 비어있지 않을 때만 로드
                    sent_ids = set(json.loads(content))
        except Exception as e:
            print(f"경고: 장부 파일 초기화 ({e})")
            sent_ids = set() # 파일이 깨졌으면 초기화

    # 2. 날짜 필터링
    now_kst = datetime.utcnow() + timedelta(hours=9)
    today_str = now_kst.strftime("%Y%m%d")
    sent_ids = {x for x in sent_ids if x.startswith(today_str)}

    # 3. 데이터 수집
    try:
        all_flights = [('도착', f) for f in get_flight_data('I')] + [('출발', f) for f in get_flight_data('O')]
    except Exception as e:
        print(f"데이터 수집 중 에러: {e}")
        all_flights = []
    
    new_count = 0
    
    # 4. 변동사항 체크
    for type_name, f in all_flights:
        try:
            raw_status = f.get('rmkKor')
            status = str(raw_status).strip() if raw_status else "예정"
            std = str(f.get('std', '0000'))
            etd = str(f.get('etd')) if f.get('etd') else std

            try:
                # 숫자 변환 시도
                std_int = int(std) if std.isdigit() else 0
                etd_int = int(etd) if etd.isdigit() else 0
                is_delayed = etd_int > std_int or "지연" in status
            except:
                is_delayed = "지연" in status

            is_cancelled = "결항" in status

            if is_cancelled or is_delayed:
                flight_num = f.get('airFln', 'Unknown')
                unique_id = f"{today_str}_{flight_num}_{status}_{etd}"
                
                if unique_id not in sent_ids:
                    airline = f.get('airlineKorean', '')
                    city = f.get('boardingKor', '') if type_name == '도착' else f.get('arrivedKor', '')
                    route = f"{city} → 제주" if type_name == '도착' else f"제주 → {city}"
                    
                    # 시간 포맷팅 안전장치
                    std_fmt = f"{std[:2]}:{std[2:]}" if len(std) >= 4 else std
                    etd_fmt = f"{etd[:2]}:{etd[2:]}" if len(etd) >= 4 else etd
                    
                    msg = (f"{'🚫' if is_cancelled else '⚠️'} *국내선 {type_name} {'결항' if is_cancelled else '지연'}*\n"
                           f"```{airline} {flight_num}\n"
                           f"{route}\n"
                           f"{std_fmt} → {etd_fmt}\n"
                           f"상태: {status}```")
                    
                    send_slack(msg)
                    sent_ids.add(unique_id)
                    new_count += 1
        except Exception as e:
            print(f"개별 항공편 처리 중 에러 (건너뜀): {e}")
            continue
    
    # 5. 변동사항 없음 알림 (새벽 시간 테스트용)
    if new_count == 0:
        current_time_str = now_kst.strftime('%H:%M')
        send_slack(f"✅ {current_time_str} 현재 지연/결항 변동사항이 없습니다.")
        print(f"변동사항 없음 알림 전송 완료 ({current_time_str})")

    # 6. 결과 저장
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(sent_ids), f, ensure_ascii=False)
    except Exception as e:
        print(f"파일 저장 실패: {e}")

    print(f"=== 실행 완료: {new_count}건 전송 ===")

if __name__ == "__main__":
    try:
        check_jeju()
    except Exception as e:
        print("치명적 에러 발생:")
        print(traceback.format_exc())
