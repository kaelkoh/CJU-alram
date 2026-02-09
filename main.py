import requests
import json
import os
from datetime import datetime, timedelta

SERVICE_KEY = os.environ.get('AIRPORT_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_URL')
DATA_FILE = 'sent_data_v6.json'

def send_slack(msg):
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
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
        items = res.json()['response']['body']['items']['item']
        return [items] if isinstance(items, dict) else items
    except:
        return []

def check_jeju():
    # [시간 제한 로직] 한국 시간 기준 06:00~22:15 사이가 아니면 종료
    # GitHub 서버 시간은 UTC이므로 9시간을 더해 한국 시간을 계산합니다.
    now_kst = datetime.utcnow() + timedelta(hours=9)
    current_hour = now_kst.hour
    
    if not (6 <= current_hour <= 22):
        print(f"현재 시간 {current_hour}시: 작동 시간이 아니므로 종료합니다.")
        return

    if not SERVICE_KEY or not SLACK_WEBHOOK_URL: return

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            sent_ids = set(json.load(f))
    else:
        sent_ids = set()

    today_str = now_kst.strftime("%Y%m%d")
    sent_ids = {x for x in sent_ids if x.startswith(today_str)}

    all_flights = [('도착', f) for f in get_flight_data('I')] + [('출발', f) for f in get_flight_data('O')]
    
    new_count = 0
    for type_name, f in all_flights:
        raw_status = f.get('rmkKor')
        status = str(raw_status).strip() if raw_status else "예정"
        std = str(f.get('std', '0000'))
        etd = str(f.get('etd')) if f.get('etd') else std

        try:
            std_int, etd_int = int(std), int(etd)
        except:
            std_int, etd_int = 0, 0

        is_cancelled = "결항" in status
        is_delayed = etd_int > std_int or "지연" in status

        if is_cancelled or is_delayed:
            flight_num = f.get('airFln', 'Unknown')
            unique_id = f"{today_str}_{flight_num}_{status}_{etd}"
            
            if unique_id not in sent_ids:
                airline = f.get('airlineKorean', '')
                city = f.get('boardingKor', '') if type_name == '도착' else f.get('arrivedKor', '')
                route = f"{city} → 제주" if type_name == '도착' else f"제주 → {city}"
                
                sched_time = f"{std[:2]}:{std[2:]}"
                etd_time = f"{etd[:2]}:{etd[2:]}"
                
                emoji = "🚫" if is_cancelled else "⚠️"
                title = f"국내선 {type_name} {'결항' if is_cancelled else '지연'} 알림"

                msg = (f"{emoji} *{title}*\n"
                       f"```{airline} {flight_num}\n"
                       f"{route}\n"
                       f"{sched_time} → {etd_time}\n"
                       f"상태: {status}```")
                
                send_slack(msg)
                sent_ids.add(unique_id)
                new_count += 1
    
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(sent_ids), f, ensure_ascii=False)
    print(f"완료: {new_count}건 전송")

if __name__ == "__main__":
    check_jeju()
