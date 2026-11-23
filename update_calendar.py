import os
import time
import math
import requests
import pytz

from datetime import datetime, timedelta
from icalendar import Calendar, Event


# ==========================================
# 1. 기본 설정
# ==========================================

TZ = pytz.timezone("Asia/Seoul")

NX = int(os.environ.get("KMA_NX") or 60)
NY = int(os.environ.get("KMA_NY") or 127)

LOCATION_NAME = os.environ.get(
    "LOCATION_NAME", "내 위치"
)

REG_ID_TEMP = os.environ.get(
    "REG_ID_TEMP", "11B10101"
)

REG_ID_LAND = os.environ.get(
    "REG_ID_LAND", "11B00000"
)

API_KEY = os.environ.get("KMA_API_KEY")

ICS_PATH = "weather.ics"
TEMP_PATH = "weather.ics.tmp"

SHORT_URL = (
    "https://apihub.kma.go.kr/api/typ02/openApi/"
    "VilageFcstInfoService_2.0/getVilageFcst"
)

MID_TEMP_URL = (
    "https://apihub.kma.go.kr/api/typ02/openApi/"
    "MidFcstInfoService/getMidTa"
)

MID_LAND_URL = (
    "https://apihub.kma.go.kr/api/typ02/openApi/"
    "MidFcstInfoService/getMidLandFcst"
)


# ==========================================
# 2. 날씨 이모지
# ==========================================

def get_weather_info(sky, pty):

    sky = str(sky)
    pty = str(pty)

    weather = {
        "1": ("🌧️", "비"),
        "2": ("🌨️", "비/눈"),
        "3": ("❄️", "눈"),
        "4": ("☔", "소나기"),
        "5": ("💧", "빗방울"),
        "6": ("🌨️", "빗방울/눈날림"),
        "7": ("❄️", "눈날림"),
    }

    if pty in weather:
        return weather[pty]

    sky_weather = {
        "1": ("☀️", "맑음"),
        "3": ("⛅", "구름많음"),
        "4": ("☁️", "흐림"),
    }

    return sky_weather.get(
        sky, ("🌡️", "정보없음")
    )


def get_mid_emoji(wf):

    if not wf:
        return "🌡️"

    wf = str(wf).replace(" ", "")

    if "소나기" in wf:
        return "☔"

    if "비" in wf:
        return "🌧️"

    if "눈" in wf:
        return "🌨️"

    if "구름많음" in wf:
        return "⛅"

    if "흐림" in wf:
        return "☁️"

    if "맑음" in wf:
        return "☀️"

    return "🌡️"


# ==========================================
# 3. 기상청 API 호출
# ==========================================

def fetch_api(url, params):

    if not API_KEY:
        raise RuntimeError(
            "KMA_API_KEY가 설정되지 않았습니다."
        )

    params = dict(params)
    params["authKey"] = API_KEY

    for attempt in range(1, 4):

        try:

            response = requests.get(
                url,
                params=params,
                timeout=25
            )

            response.raise_for_status()

            data = response.json()

            header = (
                data.get("response", {})
                .get("header", {})
            )

            if header.get("resultCode") != "00":

                print(
                    "기상청 API 오류:",
                    header.get("resultCode"),
                    header.get("resultMsg")
                )

                return None

            if not data.get(
                "response", {}
            ).get("body"):

                print("API 응답 데이터가 없습니다.")
                return None

            print(
                "API 호출 성공:",
                url.split("/")[-1]
            )

            return data

        except Exception as e:

            print(
                f"API 실패 ({attempt}/3): "
                f"{type(e).__name__}"
            )

            if attempt < 3:
                time.sleep(attempt * 3)

    return None


# ==========================================
# 4. 단기예보 발표시간 계산
# ==========================================

def get_base_datetime(now):

    release_hours = [
        2, 5, 8, 11, 14, 17, 20, 23
    ]

    effective_now = now - timedelta(minutes=10)

    valid = [
        h for h in release_hours
        if h <= effective_now.hour
    ]

    if valid:

        base_h = max(valid)

        return (
            effective_now.strftime("%Y%m%d"),
            f"{base_h:02d}00"
        )

    prev = effective_now - timedelta(days=1)

    return prev.strftime("%Y%m%d"), "2300"


# ==========================================
# 5. 중기예보 발표시간 계산
# ==========================================

def get_tmfc_candidates(now):

    effective_now = now - timedelta(minutes=30)

    if effective_now.hour < 6:

        c1 = (
            effective_now - timedelta(days=1)
        ).replace(
            hour=18, minute=0,
            second=0, microsecond=0
        )

        c2 = (
            effective_now - timedelta(days=2)
        ).replace(
            hour=18, minute=0,
            second=0, microsecond=0
        )

    elif effective_now.hour < 18:

        c1 = effective_now.replace(
            hour=6, minute=0,
            second=0, microsecond=0
        )

        c2 = (
            effective_now - timedelta(days=1)
        ).replace(
            hour=18, minute=0,
            second=0, microsecond=0
        )

    else:

        c1 = effective_now.replace(
            hour=18, minute=0,
            second=0, microsecond=0
        )

        c2 = effective_now.replace(
            hour=6, minute=0,
            second=0, microsecond=0
        )

    return [c1, c2]


# ==========================================
# 6. 기존 ICS 캐시 읽기
# ==========================================

def load_cached_events(path):

    cache = {}

    if not os.path.exists(path):
        return cache

    try:

        with open(path, "rb") as f:
            cal = Calendar.from_ical(f.read())

        for component in cal.walk():

            if component.name != "VEVENT":
                continue

            dtstart = component.get("dtstart")

            if not dtstart:
                continue

            d = dtstart.dt

            if isinstance(d, datetime):
                d = d.date()

            cache[d.strftime("%Y%m%d")] = (
                component.to_ical()
            )

        print(
            f"기존 캐시: {len(cache)}일"
        )

    except Exception as e:

        print(
            f"ICS 캐시 읽기 실패: {type(e).__name__}"
        )

    return cache


def event_from_cache(raw_ical):

    try:

        wrapped = (
            b"BEGIN:VCALENDAR\r\n"
            b"VERSION:2.0\r\n"
            + raw_ical
            + b"\r\nEND:VCALENDAR"
        )

        cal = Calendar.from_ical(wrapped)

        for component in cal.walk():

            if component.name == "VEVENT":
                return component

    except Exception as e:

        print(
            f"캐시 복원 실패: {type(e).__name__}"
        )

    return None
    # ==========================================
# 7. 단기예보 데이터 수집
# ==========================================

def get_short_forecast(now):

    base_date, base_time = get_base_datetime(now)

    print(
        f"단기예보 기준: {base_date} {base_time}"
    )

    params = {
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": NX,
        "ny": NY,
        "numOfRows": 2000,
    }

    data = fetch_api(SHORT_URL, params)

    if not data:
        return {}

    items = (
        data.get("response", {})
        .get("body", {})
        .get("items", {})
        .get("item", [])
    )

    forecast_map = {}

    for item in items:

        d = item["fcstDate"]
        t = item["fcstTime"]
        cat = item["category"]
        val = item["fcstValue"]

        forecast_map.setdefault(d, {})
        forecast_map[d].setdefault(t, {})

        forecast_map[d][t][cat] = val

    print(
        f"단기예보 수집: {len(forecast_map)}일"
    )

    return forecast_map


# ==========================================
# 8. 단기예보 캘린더 생성
# ==========================================

def create_short_events(
    cal,
    forecast_map,
    cached_events,
    now,
    today_dt,
    update_ts
):

    processed = set()

    today_str = today_dt.strftime("%Y%m%d")

    end_str = (
        today_dt + timedelta(days=3)
    ).strftime("%Y%m%d")

    defaults = {
        "TMP": "15",
        "SKY": "1",
        "PTY": "0",
        "REH": "50",
        "WSD": "1.0",
        "POP": "0",
    }

    for d_str in sorted(forecast_map):

        if d_str < today_str or d_str > end_str:
            continue

        day_data = forecast_map[d_str]

        temperatures = []

        for hour_data in day_data.values():

            if "TMP" in hour_data:

                try:
                    temperatures.append(
                        float(hour_data["TMP"])
                    )
                except (ValueError, TypeError):
                    pass

        if not temperatures:
            continue

        t_min = math.floor(min(temperatures))
        t_max = math.ceil(max(temperatures))

        rep_t = (
            "1200"
            if "1200" in day_data
            else sorted(day_data.keys())[0]
        )

        rep_emoji, _ = get_weather_info(
            day_data[rep_t].get("SKY", "1"),
            day_data[rep_t].get("PTY", "0")
        )

        # 날짜별 독립적인 초기값
        cache = defaults.copy()

        desc = []
        has_future_data = False

        for hour in range(24):

            t_str = f"{hour:02d}00"

            event_time = TZ.localize(
                datetime.strptime(
                    f"{d_str}{t_str}",
                    "%Y%m%d%H%M"
                )
            )

            if t_str in day_data:

                for cat in cache:

                    if cat in day_data[t_str]:
                        cache[cat] = day_data[t_str][cat]

            if event_time < now:
                continue

            emoji, weather = get_weather_info(
                cache["SKY"],
                cache["PTY"]
            )

            details = []

            if cache["PTY"] != "0":
                details.append(
                    f"☔{cache['POP']}%"
                )

            details.append(
                f"💧{cache['REH']}%"
            )

            details.append(
                f"🚩{cache['WSD']}m/s"
            )

            desc.append(
                f"[{hour:02d}시] {emoji} {weather} "
                f"{cache['TMP']}°C "
                f"({' '.join(details)})"
            )

            has_future_data = True

        if not has_future_data:
            continue

        event = Event()

        event.add(
            "summary",
            f"{rep_emoji} {t_min}°C/{t_max}°C"
        )

        event.add("location", LOCATION_NAME)

        desc.append(
            f"\n최종 업데이트: {update_ts} (KST)"
        )

        event.add(
            "description",
            "\n".join(desc)
        )

        event.add(
            "dtstart",
            datetime.strptime(
                d_str, "%Y%m%d"
            ).date()
        )

        event.add(
            "dtend",
            datetime.strptime(
                d_str, "%Y%m%d"
            ).date() + timedelta(days=1)
        )

        event.add(
            "uid",
            f"{d_str}@short_summary"
        )

        cal.add_component(event)

        processed.add(d_str)

        print(
            f"단기예보 생성 완료: {d_str}"
        )

    # 단기예보 실패 시 기존 데이터 재사용

    for delta in range(4):

        d_str = (
            today_dt + timedelta(days=delta)
        ).strftime("%Y%m%d")

        if d_str in processed:
            continue

        if d_str in cached_events:

            event = event_from_cache(
                cached_events[d_str]
            )

            if event:

                cal.add_component(event)

                processed.add(d_str)

                print(
                    f"단기예보 캐시 사용: {d_str}"
                )

    return processed


# ==========================================
# 9. 중기예보 데이터 수집
# ==========================================

def get_mid_forecast(now):

    for candidate in get_tmfc_candidates(now):

        tm_fc_str = candidate.strftime(
            "%Y%m%d%H%M"
        )

        print(
            f"중기예보 기준: {tm_fc_str}"
        )

        params_temp = {
            "dataType": "JSON",
            "regId": REG_ID_TEMP,
            "tmFc": tm_fc_str,
        }

        params_land = {
            "dataType": "JSON",
            "regId": REG_ID_LAND,
            "tmFc": tm_fc_str,
        }

        t_data = fetch_api(
            MID_TEMP_URL,
            params_temp
        )

        l_data = fetch_api(
            MID_LAND_URL,
            params_land
        )

        if not t_data or not l_data:
            continue

        try:

            t_items = (
                t_data["response"]["body"]
                ["items"]["item"][0]
            )

            l_items = (
                l_data["response"]["body"]
                ["items"]["item"][0]
            )

            print("중기예보 수집 성공")

            return t_items, l_items, candidate

        except (KeyError, IndexError, TypeError):

            print(
                "중기예보 데이터 형식 오류"
            )

    return None, None, None


# ==========================================
# 10. 중기예보 캘린더 생성
# ==========================================

def create_mid_events(
    cal,
    cached_events,
    now,
    today_dt,
    update_ts
):

    t_items, l_items, tm_fc_dt = get_mid_forecast(now)

    processed = set()

    cur_dt = today_dt + timedelta(days=4)
    end_dt = today_dt + timedelta(days=10)

    while cur_dt <= end_dt:

        d_str = cur_dt.strftime("%Y%m%d")

        event = None

        if t_items and l_items and tm_fc_dt:

            field_i = (
                cur_dt.date() - tm_fc_dt.date()
            ).days

            t_min = t_items.get(
                f"taMin{field_i}"
            )

            t_max = t_items.get(
                f"taMax{field_i}"
            )

            if field_i <= 7:

                wf_am = l_items.get(
                    f"wf{field_i}Am"
                )

                wf_pm = l_items.get(
                    f"wf{field_i}Pm"
                )

                rn_am = l_items.get(
                    f"rnSt{field_i}Am"
                )

                rn_pm = l_items.get(
                    f"rnSt{field_i}Pm"
                )

                wf_rep = wf_pm

            else:

                wf_am = None
                wf_pm = None
                rn_am = None
                rn_pm = None

                wf_rep = l_items.get(
                    f"wf{field_i}"
                )

            if (
                t_min is not None
                and t_max is not None
                and wf_rep is not None
            ):

                mid_desc = []

                if field_i <= 7:

                    mid_desc.append(
                        f"[오전] {get_mid_emoji(wf_am)} "
                        f"{wf_am} (☔{rn_am}%)"
                    )

                    mid_desc.append(
                        f"[오후] {get_mid_emoji(wf_pm)} "
                        f"{wf_pm} (☔{rn_pm}%)"
                    )

                else:

                    rn_st = l_items.get(
                        f"rnSt{field_i}"
                    )

                    mid_desc.append(
                        f"[종일] {get_mid_emoji(wf_rep)} "
                        f"{wf_rep} (☔{rn_st}%)"
                    )

                mid_desc.append(
                    f"\n최종 업데이트: {update_ts} (KST)"
                )

                event = Event()

                event.add(
                    "summary",
                    f"{get_mid_emoji(wf_rep)} "
                    f"{t_min}/{t_max}°C"
                )

                event.add(
                    "location",
                    LOCATION_NAME
                )

                event.add(
                    "description",
                    "\n".join(mid_desc)
                )

                event.add(
                    "dtstart",
                    cur_dt.date()
                )

                event.add(
                    "dtend",
                    (cur_dt + timedelta(days=1)).date()
                )

                event.add(
                    "uid",
                    f"{d_str}@mid"
                )

        # 새 데이터가 없으면 기존 캐시 사용

        if event is None and d_str in cached_events:

            event = event_from_cache(
                cached_events[d_str]
            )

            if event:
                print(
                    f"중기예보 캐시 사용: {d_str}"
                )

        if event is not None:

            cal.add_component(event)

            processed.add(d_str)

            print(
                f"중기예보 생성 완료: {d_str}"
            )

        cur_dt += timedelta(days=1)

    return processed
    # ==========================================
# 11. ICS 파일 안전 저장
# ==========================================

def save_calendar(cal):

    events = [
        c for c in cal.walk()
        if c.name == "VEVENT"
    ]

    if not events:
        raise RuntimeError(
            "날씨 데이터가 없습니다. "
            "기존 weather.ics를 유지합니다."
        )

    # 임시 파일에 먼저 저장
    with open(TEMP_PATH, "wb") as f:
        f.write(cal.to_ical())

    # 저장된 ICS 파일 검증
    with open(TEMP_PATH, "rb") as f:
        check = Calendar.from_ical(f.read())

    check_events = [
        c for c in check.walk()
        if c.name == "VEVENT"
    ]

    if not check_events:
        raise RuntimeError(
            "ICS 검증 실패. 기존 파일을 유지합니다."
        )

    # 검증 성공 시에만 기존 파일 교체
    os.replace(TEMP_PATH, ICS_PATH)

    print(
        f"ICS 저장 성공: {len(check_events)}개 이벤트"
    )


# ==========================================
# 12. 메인 프로그램
# ==========================================

def main():

    if not API_KEY:
        raise RuntimeError(
            "KMA_API_KEY가 없습니다. "
            "GitHub Secrets를 확인하세요."
        )

    now = datetime.now(TZ)

    today_dt = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    update_ts = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("=" * 45)
    print("기상청 날씨 캘린더 업데이트")
    print(f"지역: {LOCATION_NAME}")
    print(f"시간: {update_ts} KST")
    print("=" * 45)

    # 기존 데이터 읽기
    cached_events = load_cached_events(ICS_PATH)

    # 새 캘린더 생성
    cal = Calendar()

    cal.add(
        "prodid",
        "-//Weather Calendar//KMA//KR"
    )

    cal.add("version", "2.0")

    cal.add(
        "X-WR-CALNAME",
        "기상청 날씨"
    )

    cal.add(
        "X-WR-TIMEZONE",
        "Asia/Seoul"
    )

    # --------------------------------------
    # 단기예보: 오늘 ~ 3일 후
    # --------------------------------------

    print("\n[단기예보 시작]")

    forecast_map = get_short_forecast(now)

    short_dates = create_short_events(
        cal,
        forecast_map,
        cached_events,
        now,
        today_dt,
        update_ts
    )

    # --------------------------------------
    # 중기예보: 4일 후 ~ 10일 후
    # --------------------------------------

    print("\n[중기예보 시작]")

    mid_dates = create_mid_events(
        cal,
        cached_events,
        now,
        today_dt,
        update_ts
    )

    # --------------------------------------
    # 결과 확인
    # --------------------------------------

    processed_dates = short_dates | mid_dates

    print("\n" + "=" * 45)

    print(
        f"단기예보 날짜: {len(short_dates)}일"
    )

    print(
        f"중기예보 날짜: {len(mid_dates)}일"
    )

    print(
        f"전체 날짜: {len(processed_dates)}일"
    )

    # 데이터가 전혀 없으면 기존 파일 보호
    if not processed_dates:
        raise RuntimeError(
            "예보 데이터와 기존 캐시가 모두 없습니다. "
            "기존 weather.ics를 유지합니다."
        )

    # 정상 데이터만 저장
    save_calendar(cal)

    print("=" * 45)
    print("날씨 캘린더 업데이트 성공!")
    print("=" * 45)


# ==========================================
# 13. 프로그램 실행
# ==========================================

if __name__ == "__main__":

    try:
        main()

    finally:

        if os.path.exists(TEMP_PATH):
            os.remove(TEMP_PATH)
