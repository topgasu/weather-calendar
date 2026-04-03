import os
import requests
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# --- [1. 설정] ---
NX, NY = 60, 127
LOCATION_NAME = "봉화산로 193"
API_KEY = os.environ.get('KMA_API_KEY')

def get_emoji(sky, pty):
    sky, pty = str(sky), str(pty)
    if pty != '0':
        if pty in ['1', '4']: return "🌧️"
        if pty == '2': return "🌨️"
        if pty == '3': return "❄️"
    if sky == '1': return "☀️"
    if sky == '3': return "⛅"
    if sky == '4': return "☁️"
    return "🌡️"

def fetch_short_term(date, time):
    """특정 시점의 단기예보를 가져옴"""
    url = f"https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst?dataType=JSON&base_date={date}&base_time={time}&nx={NX}&ny={NY}&authKey={API_KEY}"
    try:
        res = requests.get(url).json()
        return res['response']['body']['items']['item']
    except: return []

def main():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    cal = Calendar()
    cal.add('X-WR-CALNAME', '기상청 날씨')
    cal.add('X-WR-TIMEZONE', 'Asia/Seoul')

    # 오늘 0시부터 데이터를 채우기 위해 어제 23시 예보부터 긁어옵니다.
    yesterday = (now - timedelta(days=1)).strftime('%Y%m%d')
    today = now.strftime('%Y%m%d')
    
    # 여러 시간대 예보를 합쳐서 24시간 빈틈을 메웁니다.
    all_items = []
    all_items.extend(fetch_short_term(yesterday, "2300"))
    all_items.extend(fetch_short_term(today, "0200"))
    all_items.extend(fetch_short_term(today, "0500"))
    all_items.extend(fetch_short_term(today, "0800"))

    forecast_map = {}
    for it in all_items:
        d, t, cat, val = it['fcstDate'], it['fcstTime'], it['category'], it['fcstValue']
        if d not in forecast_map: forecast_map[d] = {}
        if t not in forecast_map[d]: forecast_map[d][t] = {}
        forecast_map[d][t][cat] = val

    # 11일치 루프
    for i in range(11):
        target_dt = now + timedelta(days=i)
        d_str = target_dt.strftime('%Y%m%d')
        event = Event()
        
        if d_str in forecast_map:
            d_data = forecast_map[d_str]
            times = sorted(d_data.keys())
            
            # 기온(TMP) 데이터만 추출하여 최저/최고 계산
            tmps = [float(d_data[t]['TMP']) for t in times if 'TMP' in d_data[t]]
            if not tmps: continue
            t_min, t_max = int(min(tmps)), int(max(tmps))
            
            # 제목 설정
            mid_t = "1200" if "1200" in d_data else times[len(times)//2]
            rep_em = get_emoji(d_data[mid_t].get('SKY', '1'), d_data[mid_t].get('PTY', '0'))
            event.add('summary', f"{rep_em} {t_min}°C / {t_max}°C")
            
            # 본문 상세 (이미지 스타일)
            desc = [f"📍 {LOCATION_NAME}\n"]
            for t in times:
                it = d_data[t]
                em = get_emoji(it.get('SKY', '1'), it.get('PTY', '0'))
                # 습도 변수가 REH가 아닐 경우 대비해 안전하게 가져옴
                hum = it.get('REH') or it.get('HUM') or "0"
                pop = it.get('POP', '0')
                wsd = it.get('WSD', '0')
                tmp = it.get('TMP', '0')
                
                line = f"[{t[:2]}h - {int(t[:2])+3:02d}h] {em} {tmp}°C (☔{pop}% 💧{hum}% 💨{wsd}m/s)"
                desc.append(line)
            
            desc.append(f"\nLast update: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            event.add('description', "\n".join(desc))
        else:
            event.add('summary', "⛅ 중기 예보 확인")
            event.add('description', "상세 예보는 기상청 홈페이지를 참조하세요.")

        event.add('dtstart', target_dt.date())
        event.add('dtend', (target_dt + timedelta(days=1)).date())
        event.add('uid', f"{d_str}@kma_weather")
        cal.add_component(event)

    with open('weather.ics', 'wb') as f:
        f.write(cal.to_ical())
    print("✅ 데이터 누락 및 습도 문제 해결 완료!")

if __name__ == "__main__":
    main()
