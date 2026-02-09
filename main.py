import requests
import json
import os
from datetime import datetime, timedelta

SERVICE_KEY = os.environ.get('AIRPORT_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_URL')

def send_slack(msg):
    try:
        if SLACK_WEBHOOK_URL:
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
    except Exception as e:
        print(f"슬랙 전송 에러: {e}")

def get_flight_data(io_type):
    url = "http://openapi.airport.co.kr/service/rest/FlightStatusList/getFlightStatusList"
    params = {
        'serviceKey': SERVICE_KEY,
        'schLineType': 'D', # 국내선만 조회
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
    except:
        return []

def process_flight(f, flight_type, summary):
    try:
        raw_status = f.get('rmkKor')
        status = str(raw_status).strip() if raw_status else "예정"
        
        std = str(f.get('std', '0000'))
        etd = str(f.get('etd')) if f.get('etd') else std
        
        is_cancelled = "결항" in status
        try:
            is_delayed = int(etd) > int(std) or "지연" in status
        except:
            is_delayed = "지연" in status

        if is_cancelled or is_delayed:
            airline = f.get('airlineKorean', '')
            flight_num = f.get('airFln', '')
            
            # 시간 포맷 (0730 -> 07:30)
            std_fmt = f"{std[:2]}:{std[2:]}"
            etd_fmt = f"{etd[:2]}:{etd[2:]}"
            
            # 표기 양식: 대한항공 KE123 (07:00→07:10)
            info = f"{airline} {flight_num} ({std_fmt}→{etd_fmt})"

            if is_cancelled:
                summary[f"{flight_type}_CANCEL"].append(info)
            else:
                summary[f"{flight_type}_DELAY"].append(info)
    except:
        pass

def check_jeju():
    # [시간 제한] 한국 시간 06시~22시 외에는 작동 중지
    now_kst = datetime.utcnow() + timedelta(hours=9)
    if not (6 <= now_kst.hour <= 22):
        print(f"현재 {now_kst.hour}시: 야간 정지 시간입니다.")
        return

    summary = {
        "ARR_DELAY": [], "ARR_CANCEL": [], # 도착 지연/결항
        "DEP_DELAY": [], "DEP_CANCEL": []  # 출발 지연/결항
    }

    # 데이터 수집 및 분류
    print("데이터 조회 중...")
    for f in get_flight_data('I'): process_flight(f, 'ARR', summary)
    for f in get_flight_data('O'): process_flight(f, 'DEP', summary)

    # 메시지 작성
    current_time = now_kst.strftime('%H:%M')
    msg = f"📊 *제주공항 국내선 운항 요약 ({current_time})*\n"
    has_data = False

    sections = [
        ("🛬 도착 지연", summary["ARR_DELAY"]),
        ("🚫 도착 결항", summary["ARR_CANCEL"]),
        ("🛫 출발 지연", summary["DEP_DELAY"]),
        ("🚫 출발 결항", summary["DEP_CANCEL"])
    ]

    for title, data_list in sections:
        if data_list:
            has_data = True
            # 명단이 많으면 쉼표로 연결해서 보여줌
            content = ", ".join(data_list)
            msg += f"\n*{title}*\n```{content}```"

    # 변동사항 없을 때 안내
    if not has_data:
        msg += "\n✅ 현재 지연/결항된 항공편이 없습니다."

    send_slack(msg)
    print("요약 전송 완료")

if __name__ == "__main__":
    check_jeju()
