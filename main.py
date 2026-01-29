import requests
import json
import os
from datetime import datetime

# GitHub Secrets 환경변수 불러오기
SERVICE_KEY = os.environ.get('AIRPORT_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_URL')
DATA_FILE = 'sent_data.json'

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

    # 제주공항 국내선 도착편 조회 (06:00 ~ 23:59)
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
            print("데이터가 없거나 응답 형식 오류 (아직 운항 정보가 없을 수 있음)")
            pass

        if isinstance(items, dict):
            items = [items]
        
        new_count = 0
        
        for flight in items:
            status = flight.get('remark', '')
            
            # '지연' 또는 '결항' 상태일 때만 알림
            if status and ('지연' in status or '결항' in status):
                flight_num = flight.get('airFln', 'Unknown')
                
                # [중요] 스케줄 시간(std)과 변경 예정 시간(est)을 모두 가져옴
                std = flight.get('std', '0000')      # 당초 예정 시간
                est = flight.get('est', std)         # 변경된 시간 (없으면 당초 시간 사용)
                
                # 고유 ID 생성 규칙 변경: 날짜_편명_상태_변경시간
                # 이제 시간이 1분이라도 바뀌면 새로운 알림으로 인식합니다.
                unique_id = f"{today_str}_{flight_num}_{status}_{est}"
                
                if unique_id not in sent_ids:
                    airline = flight.get('airlineKorean', '')
                    origin = flight.get('boardingKor', '')
                    
                    # 시간 포맷팅 (1430 -> 14:30)
                    sched_time = f"{std[:2]}:{std[2:]}"
                    est_time = f"{est[:2]}:{est[2:]}"
                    
                    emoji = "🚫" if "결항" in status else "⚠️"
                    
                    # 메시지에 변경된 시간을 강조해서 보여줌
                    msg = (f"{emoji} *제주공항 {status} 알림*\n"
                           f"✈️ {airline} {flight_num}\n"
                           f"🛫 {origin} → ⏰ {sched_time} (변경: {est_time})")
                    
                    send_slack(msg)
                    sent_ids.add(unique_id)
                    new_count += 1
        
        save_sent_data(sent_ids)
        print(f"실행 완료: 신규 알림 {new_count}건 전송됨")

    except Exception as e:
        print(f"시스템 에러: {e}")

if __name__ == "__main__":
    check_jeju()
