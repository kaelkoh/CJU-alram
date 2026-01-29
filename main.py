import requests
import json
import os
from datetime import datetime

# GitHub Secrets 환경변수 불러오기
SERVICE_KEY = os.environ.get('AIRPORT_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_URL')
DATA_FILE = 'sent_data_v2.json'

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
    
    # 오늘 날짜가 아닌 데이터는 메모리에서 정리
    sent_ids = {x for x in sent_ids if x.startswith(today_str)}

    # 제주공항 국내선 도착편 조회
    url = "http://openapi.airport.co.kr/service/rest/FlightStatusList/getFlightStatusList"
    params = {
        'serviceKey': SERVICE_KEY,
        'schLineType': 'D',      # 국내선
        'schIOType': 'I',        # 도착
        'schAirCode': 'CJU',     # 제주공항
        'schStTime': '0600',     # 06시부터
        'schEdTime': '2359',     # 24시까지
        'numOfRows': '500',
        '_type': 'json'
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        items = []
        
        try:
            data = res.json()
            items = data['response']['body']['items']['item']
        except (KeyError, TypeError, json.JSONDecodeError):
            print("데이터가 없거나 응답 형식 오류")
            pass

        if isinstance(items, dict):
            items = [items]
        
        new_count = 0
        
        for flight in items:
            status = flight.get('rmkKor', '')     # 상태 (도착, 지연, 결항 등)
            std = flight.get('std', '0000')       # 예정시간
            etd = flight.get('etd')               # 변경시간
            
            if not etd: 
                etd = std

            # 시간 비교를 위해 숫자로 변환 (예: "1230" -> 1230)
            try:
                std_int = int(std)
                etd_int = int(etd)
            except:
                std_int = 0
                etd_int = 0

            # [핵심 로직]
            # 1. "결항"이거나 "지연" 글자가 있는 경우 무조건 포함
            # 2. 시간이 "뒤로 밀린 경우(지연)" 포함 (etd > std)
            # 3. 조기 도착(etd < std)은 여기서 자동 제외됨
            is_cancelled = "결항" in str(status)
            is_delayed_status = "지연" in str(status)
            is_time_delayed = etd_int > std_int

            if is_cancelled or is_delayed_status or is_time_delayed:
                flight_num = flight.get('airFln', 'Unknown')
                
                # 고유 ID: 날짜_편명_상태_변경시간
                unique_id = f"{today_str}_{flight_num}_{status}_{etd}"
                
                if unique_id not in sent_ids:
                    airline = flight.get('airlineKorean', '')
                    origin = flight.get('boardingKor', '')
                    
                    # 시간 포맷팅 (1210 -> 12:10)
                    sched_time = f"{std[:2]}:{std[2:]}"
                    etd_time = f"{etd[:2]}:{etd[2:]}"
                    
                    # 제목 및 이모지 설정
                    if is_cancelled:
                        title = "항공편 결항 알림"
                        emoji = "🚫"
                    else:
                        title = "항공편 지연 알림"
                        emoji = "⚠️"

                    # 메시지 포맷 작성 (요청하신 형태)
                    msg = (f"{emoji} *{title}*\n"
                           f"{airline} {flight_num}\n"
                           f"{origin} → 제주\n"
                           f"{sched_time} → {etd_time}\n"
                           f"상태: {status}")
                    
                    send_slack(msg)
                    sent_ids.add(unique_id)
                    new_count += 1
        
        save_sent_data(sent_ids)
        print(f"실행 완료: 신규 알림 {new_count}건 전송됨")

    except Exception as e:
        print(f"시스템 에러: {e}")

if __name__ == "__main__":
    check_jeju()
