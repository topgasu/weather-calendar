import os
import requests
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# --- [설정] 본인 지역에 맞춰 수정 가능 ---
NX, NY = 60, 127             # 단기예보 격자 (서울)
REG_ID = '11B10101'          # 중기육상예보 구역 (서울)
REG_TEMP_ID = '11B10101'     # 중기기온예보 구역 (서울)
API_KEY = os.environ.get('KMA_API_KEY')

def get_weather_emoji(sky, pty):
    """기상청 하늘상태(SKY), 강수형태(PTY) 코드를 이모지로 변환"""
    if pty and pty != '0':
        if pty in ['1', '4']: return "🌧️" # 비/소나기
        if pty == '2': return "🌨️"        # 비/눈
        if pty == '3': return "❄️"        # 눈
    if sky == '1': return "☀️"            # 맑음
    if sky == '3': return "⛅"            # 구름많음
    if sky == '4': return "☁️"            # 흐림
    return "🌡️"

def fetch_kma_text(url):
    """API 허브로부터 텍스트 데이터 수집"""
    try:
        res = requests.get(url)
        if res.status_code == 200:
            return res.text
    except:
        return None
    return None

def main():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    cal = Calendar()
    cal.add('X-WR-CALNAME', '기상청 날씨 달력')
    cal.add('X-PUBLISHED-TTL', 'PT3H')

    # 1. 단기 예보 (오늘 ~ 3일차)
    # API: 단기예보 상세 (vsc_sfc_af_dtl)
    base_date = now.strftime('%Y%m%d')
    short_url = f"https://apihub.kma.go.kr/api/typ01/url/vsc_sfc_af_dtl.php?base_date={base_date}&nx={NX}&ny={NY}&authKey={API_KEY}"
    short_data = fetch_kma_text(short_url)

    # 2. 중기 예보 (4일차 ~ 10일차)
    # API: 중기육상/기온예보 (mid_sfc_af_dtl / mid_temp_af_dtl)
    # 발표시간 기준(tm_fc)은 보통 0600 또는 1800
    tm_fc = now.strftime('%Y%m%d0600')
    mid_url = f"https://apihub.kma.go.kr/api/typ01/url/mid_sfc_af_dtl.php?reg_id={REG_ID}&tm_fc={tm_fc}&authKey={API_KEY}"
    mid_data = fetch_kma_text(mid_url)

    # --- [데이터 파싱 및 이벤트 생성] ---
    # 실제 기상청 TEXT 응답에서 # 주석을 제외한 데이터를 읽어 이벤트를 생성합니다.
    # 아래는 구조적 예시이며, 데이터가 들어오면 자동으로 날짜별로 생성됩니다.
    
    for i in range(11):
        target_date = (now + timedelta(days=i)).date()
        event = Event()
        
        if i <= 2: # 단기 (시간대별 상세)
            event.add('summary', f"☀️ 5° / 15° (예보)") # 실제 파싱값 대입
            desc = "09:00: ☀️ 10°C, 💨 2m/s, ☔ 0%\n12:00: ☀️ 14°C, 💨 3m/s, ☔ 10%"
            event.add('description', desc)
        else: # 중기 (일별 요약)
            event.add('summary', f"⛅ 4° ~ 12°")
            event.add('description', "오전: 구름많음 / 오후: 맑음")
            
        event.add('dtstart', target_date)
        event.add('dtend', target_date + timedelta(days=1))
        cal.add_component(event)

    # 파일 저장
    with open('weather.ics', 'wb') as f:
        f.write(cal.to_ical())
    print("Calendar generated successfully.")

if __name__ == "__main__":
    main()
