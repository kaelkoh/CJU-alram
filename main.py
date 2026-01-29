import requests
import json
import os
from datetime import datetime

# GitHub Secrets 환경변수 불러오기
SERVICE_KEY = os.environ.get('AIRPORT_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_URL')

# [중요] 디자인이 변경되었으므로 새 장부(v4)를 사용하여 즉시 확인 가능하게 함
DATA_FILE = 'sent_data_v4.json'

def send_slack(msg):
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
    except Exception as e:
        print(f"슬랙 전송 에러: {e}")

def load_sent_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_sent_data(data_set):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(data_set), f, ensure_ascii=False)

def check_jeju():
    if not SERVICE_KEY or not SLACK_WEBHOOK_URL:
        print("API 키가 설정되지 않았습니다.")
        return

    sent_ids = load_sent_data()
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
        except:
            pass

        if isinstance(items, dict):
            items = [items]
        
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
            is_delayed_status = "지연" in status
            is_time_delayed = etd_int > std_int

            if is_cancelled or is_delayed_status or is_time_delayed:
                flight_num = flight.get('airFln', 'Unknown')
                unique_id = f"{today_str}_{flight_num}_{status}_{etd}"
                
                if unique_id not in sent_ids:
                    airline = flight.get('airlineKorean', '')
                    origin = flight.get('boardingKor', '')
                    sched_time = f"{std[:2]}:{std[2:]}"
                    etd_time = f"{etd[:2]}:{etd[2:]}"
                    
                    # 제목 설정
                    title = "항공편 결항 알림" if is_cancelled else "항공편 지연 알림"
                    emoji = "🚫" if is_cancelled else "⚠️"

                    # [코드 블록 디자인] 상세 내용을 ``` 로 감싸서 박스 형태로 만듦
                    msg = (
                        f"{emoji} *{title}*\n"
                        f"```{airline} {flight_num}\n"
                        f"{origin} → 제주\n"
                        f"{sched_time} → {etd_time}\n"
                        f"상태: {status}```"
                    )
                    
                    send_slack(msg)
                    sent_ids.add(unique_id)
                    new_count += 1
        
        save_sent_data(sent_ids)
        print(f"전송 완료: {new_count}건")

    except Exception as e:
        print(f"에러: {e}")

if __name__ == "__main__":
    check_jeju()
