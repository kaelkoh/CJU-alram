import requests
import json
import os
from datetime import datetime

SERVICE_KEY = os.environ.get('AIRPORT_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_URL')

# 장부 파일 (v5로 업데이트)
DATA_FILE = 'sent_data_v5.json'
# 마지막 알림 시간 체크 파일
LAST_NOTI_FILE = 'last_noti_time.json'

def send_slack(msg):
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
    except Exception as e:
        print(f"슬랙 전송 에러: {e}")

def load_json(filename, default_val):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default_val

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def check_jeju():
    if not SERVICE_KEY or not SLACK_WEBHOOK_URL:
        print("API 설정 오류")
        return

    # 데이터 로드
    sent_ids_list = load_json(DATA_FILE, [])
    sent_ids = set(sent_ids_list)
    last_noti_data = load_json(LAST_NOTI_FILE, {"time": datetime.now().isoformat()})
    
    today_str = datetime.now().strftime("%Y%m%d")
    sent_ids = {x for x in sent_ids if x.startswith(today_str)}

    url = "http://openapi.airport.co.kr/service/rest/FlightStatusList/getFlightStatusList"
    params = {
        'serviceKey': SERVICE_KEY,
        'schLineType': 'D',
        'schIOType': 'I',
        'schAirCode': 'CJU',
        'schStTime': '0600',
        'schEdTime': '2359',
        'numOfRows': '500',
        '_type': 'json'
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        items = []
        try:
            data = res.json()
            items = data['response']['body']['items']['item']
        except: pass

        if isinstance(items, dict): items = [items]
        
        new_count = 0
        for flight in items:
            raw_status = flight.get('rmkKor')
            status = str(raw_status).strip() if raw_status else "예정"
            std = str(flight.get('std', '0000'))
            etd = str(flight.get('etd')) if flight.get('etd') else std

            try:
                std_int, etd_int = int(std), int(etd)
            except:
                std_int, etd_int = 0, 0

            is_cancelled = "결항" in status
            is_delayed = etd_int > std_int or "지연" in status

            if is_cancelled or is_delayed:
                flight_num = flight.get('airFln', 'Unknown')
                unique_id = f"{today_str}_{flight_num}_{status}_{etd}"
                
                if unique_id not in sent_ids:
                    airline = flight.get('airlineKorean', '')
                    origin = flight.get('boardingKor', '')
                    sched_time = f"{std[:2]}:{std[2:]}"
                    etd_time = f"{etd[:2]}:{etd[2:]}"
                    
                    header = "🚫 *항공편 결항 알림*" if is_cancelled else "⚠️ *항공편 지연 알림*"
                    msg = (f"{header}\n"
                           f"```{airline} {flight_num}\n"
                           f"{origin} → 제주\n"
                           f"{sched_time} → {etd_time}\n"
                           f"상태: {status}```")
                    
                    send_slack(msg)
                    sent_ids.add(unique_id)
                    new_count += 1

        # 결과 저장
        save_json(DATA_FILE, list(sent_ids))
        
        current_time = datetime.now()
        
        if new_count > 0:
            # 새로운 알림이 있었으면 시간 갱신
            save_json(LAST_NOTI_FILE, {"time": current_time.isoformat()})
        else:
            # 새로운 알림이 없었을 때, 마지막 알림으로부터 1시간 지났는지 체크
            last_time = datetime.fromisoformat(last_noti_data["time"])
            diff_seconds = (current_time - last_time).total_seconds()
            
            if diff_seconds >= 3600: # 1시간(3600초)
                send_slack("✅ *항공편 지연/결항 변동사항 없음*")
                # 메시지 보낸 후 시간 다시 갱신 (1시간 뒤에 또 보내도록)
                save_json(LAST_NOTI_FILE, {"time": current_time.isoformat()})

        print(f"완료: 신규 {new_count}건")

    except Exception as e:
        print(f"에러: {e}")

if __name__ == "__main__":
    check_jeju()
