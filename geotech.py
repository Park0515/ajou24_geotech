import pandas as pd
import numpy as np
import folium
from folium import IFrame, Element
import plotly.graph_objects as go
import os

# 한글 폰트 설정 (맑은 고딕 사용)
font_name = 'Malgun Gothic'

#폴더 경로 설정
curDir = os.path.dirname(os.path.abspath(__file__))

# 데이터 불러오기
try:
    stations = pd.read_csv(os.path.join(curDir,'station_with_region.csv'), encoding='utf-8')
except UnicodeDecodeError:
    stations = pd.read_csv(os.path.join(curDir,'station_with_region.csv'), encoding='cp949')
stations = stations.rename(columns={'고유역번호(외부역코드)': '고유역번호'})

try:
    count2022 = pd.read_csv(os.path.join(curDir,'2022_count.csv'), encoding='utf-8')
except UnicodeDecodeError:
    count2022 = pd.read_csv(os.path.join(curDir,'2022_count.csv'), encoding='cp949')
count2022 = count2022.rename(columns={'고유역번호(외부역코드)': '고유역번호'})

try:
    count2023 = pd.read_csv(os.path.join(curDir,'2023_count.csv'), encoding='utf-8')
except UnicodeDecodeError:
    count2023 = pd.read_csv(os.path.join(curDir,'2023_count.csv'), encoding='cp949')
count2023 = count2023.rename(columns={'고유역번호(외부역코드)': '고유역번호'})

# 매출 데이터 로드
try:
    rev2022 = pd.read_csv(os.path.join(curDir,'2022_매출.csv'), encoding='cp949')
except UnicodeDecodeError:
    rev2022 = pd.read_csv(os.path.join(curDir,'2022_매출.csv'), encoding='utf-8')
try:
    rev2023 = pd.read_csv(os.path.join(curDir,'2023_매출.csv'), encoding='cp949')
except UnicodeDecodeError:
    rev2023 = pd.read_csv(os.path.join(curDir,'2023_매출.csv'), encoding='utf-8')

# 연월 -> datetime
for df in [count2022, count2023]:
    df['연월'] = df['연월'].astype(str)
    df['date'] = df['연월'].apply(lambda x: pd.to_datetime('20' + x, format='%Y%m'))

all_months = pd.date_range(start='2022-01-01', end='2023-12-01', freq='MS')

# 연도별 합계
total2022 = count2022[count2022['date'].dt.year == 2022].groupby('고유역번호')['승하차인원수'].sum().reset_index()
total2022.columns = ['고유역번호', '총승하차_2022']
total2023 = count2023[count2023['date'].dt.year == 2023].groupby('고유역번호')['승하차인원수'].sum().reset_index()
total2023.columns = ['고유역번호', '총승하차_2023']

# 병합
merged = stations.merge(total2022, on='고유역번호', how='left')
merged = merged.merge(total2023, on='고유역번호', how='left')
merged['총승하차_2022'] = merged['총승하차_2022'].fillna(0)
merged['총승하차_2023'] = merged['총승하차_2023'].fillna(0)

# 증가율
merged['증가율'] = np.where(
    merged['총승하차_2022'] == 0, 0,
    (merged['총승하차_2023'] - merged['총승하차_2022']) / merged['총승하차_2022']
)
max_rate = merged['증가율'].abs().max()
if max_rate == 0:
    max_rate = 1

# 마커 반경 계산 (5~20)
min_count = merged['총승하차_2023'].min()
max_count = merged['총승하차_2023'].max()
count_range = max_count - min_count if max_count != min_count else 1
merged['반경'] = merged['총승하차_2023'].apply(lambda x: 5 + (x - min_count) / count_range * 15)

# Folium 지도 생성
seoul_map = folium.Map(location=[37.5665, 126.9780], zoom_start=11)
map_name = seoul_map.get_name()

marker_js = {}
for idx, row in merged.iterrows():
    lat, lon = row['위도'], row['경도']
    station_name = row['역명']
    station_id = row['고유역번호']
    line = row['호선']
    r1, r2, r3 = row['region_1depth_name'], row['region_2depth_name'], row['region_3depth_name']
    region_code = row['region_code']
    rate = row['증가율']
    radius = row['반경']
    base_color = 'blue' if rate > 0 else ('red' if rate < 0 else 'gray')
    opacity = min(abs(rate) / max_rate, 1)
    fill_opacity = min(0.3 + 0.7 * opacity, 1)

    # 팝업 내 HTML: 역 정보
    info_html = f"""
    <div style='font-family:{font_name};'>
      <b>{station_name}역, {line}호선</b><br>
      {r1} {r2} {r3}
    </div>
    <hr style='margin:5px 0;'/>
    """

    # 그래프 생성: 승하차(꺾은선) + 매출(꺾은선)
    def make_chart(mid, rcode):
        # 1) 승하차 월별 데이터
        df2 = count2022[(count2022['고유역번호'] == mid) & (count2022['date'].dt.year == 2022)][['date', '승하차인원수']]
        df3 = count2023[(count2023['고유역번호'] == mid) & (count2023['date'].dt.year == 2023)][['date', '승하차인원수']]
        df_all = pd.concat([df2, df3])
        df_monthly = df_all.groupby('date')['승하차인원수'].sum().reindex(all_months, fill_value=0).reset_index()
        df_monthly.columns = ['date', '승하차인원수']

        # 2) 매출 월별 데이터
        df_rev2 = rev2022[rev2022['행정동_코드'] == rcode][['기준_년분기_코드', '당월_매출_금액']]
        df_rev3 = rev2023[rev2023['행정동_코드'] == rcode][['기준_년분기_코드', '당월_매출_금액']]
        df_rev_all = pd.concat([df_rev2, df_rev3])
        df_rev_all['date'] = pd.to_datetime(df_rev_all['기준_년분기_코드'].astype(str), format='%Y%m')
        df_monthly_rev = df_rev_all.groupby('date')['당월_매출_금액'].sum().reset_index()

        # 3) 상관계수 계산 (피어슨)
        merged_month = pd.merge(
            df_monthly[['date', '승하차인원수']],
            df_monthly_rev[['date', '당월_매출_금액']],
            on='date', how='inner'
        )
        if merged_month.empty or merged_month['당월_매출_금액'].isnull().all():
            pearson_text = "피어슨 상관계수: 계산 불가"
        else:
            pearson_corr = merged_month['승하차인원수'].corr(merged_month['당월_매출_금액'])
            if pd.isna(pearson_corr):
                pearson_text = "피어슨 상관계수: 계산 불가"
            else:
                pearson_text = f"피어슨 상관계수: {pearson_corr:.3f}"

        # 4) Plotly Figure 구성
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_monthly['date'],
            y=df_monthly['승하차인원수'],
            mode='lines+markers',
            name='승하차인원수',
            line=dict(color='royalblue')
        ))
        fig.add_trace(go.Scatter(
            x=df_monthly_rev['date'],
            y=df_monthly_rev['당월_매출_금액'],
            mode='lines+markers',
            name='월별 매출',
            line=dict(color='indianred'),
            yaxis='y2'
        ))
        fig.update_layout(
            title=f"<b>{station_name} 월별 승하차 & 매출</b>",
            xaxis=dict(title='연월', tickformat='%Y-%m'),
            yaxis=dict(title='승하차인원수'),
            yaxis2=dict(
                title='매출금액 (₩)',
                overlaying='y',
                side='right',
                tickformat=','
            ),
            legend=dict(x=0.01, y=0.99),
            template='plotly_white',
            font=dict(family=font_name),
            margin=dict(l=40, r=40, t=40, b=80),
            hovermode='x unified',
            height=450  # <- 그래프 세로 높이 조정 (기존보다 확실히 줄어듦)
        )

        fig_html = fig.to_html(
            full_html=False,
            include_plotlyjs='cdn',
            config={'displayModeBar': False}
        )
        corr_html = f"<div style='margin-top:8px; font-family:{font_name}; font-size:18px; color:#555; text-align:center;'><b>{pearson_text}</b></div>"
        return fig_html + corr_html


    chart_html = make_chart(station_id, region_code)
    full_html = info_html + chart_html

    iframe = IFrame(html=full_html, width=820, height=600)
    popup = folium.Popup(iframe, max_width=820)

    marker = folium.CircleMarker(
        location=(lat, lon),
        radius=radius,
        color=base_color,
        weight=1,
        fill=True,
        fill_color=base_color,
        fill_opacity=fill_opacity,
        popup=popup
    ).add_to(seoul_map)
    marker_js[str(station_id)] = marker.get_name()

# TOP3 증가율/감소율 추출
sorted_df = merged.sort_values('증가율', ascending=False)
top_inc = sorted_df.head(3)
top_dec = sorted_df.tail(3)

# 전체 역의 월별 피어슨 상관계수 계산 (사이드바)
pearson_list = []
for idx, row in merged.iterrows():
    mid = row['고유역번호']
    rcode = row['region_code']
    df2 = count2022[(count2022['고유역번호'] == mid) & (count2022['date'].dt.year == 2022)][['date', '승하차인원수']]
    df3 = count2023[(count2023['고유역번호'] == mid) & (count2023['date'].dt.year == 2023)][['date', '승하차인원수']]
    df_all = pd.concat([df2, df3])
    df_monthly = df_all.groupby('date')['승하차인원수'].sum().reindex(all_months, fill_value=0).reset_index()
    df_monthly.columns = ['date', '승하차인원수']

    df_rev2 = rev2022[rev2022['행정동_코드'] == rcode][['기준_년분기_코드', '당월_매출_금액']]
    df_rev3 = rev2023[rev2023['행정동_코드'] == rcode][['기준_년분기_코드', '당월_매출_금액']]
    df_rev_all = pd.concat([df_rev2, df_rev3])
    df_rev_all['date'] = pd.to_datetime(df_rev_all['기준_년분기_코드'].astype(str), format='%Y%m')
    df_monthly_rev = df_rev_all.groupby('date')['당월_매출_금액'].sum().reset_index()

    merged_month = pd.merge(
        df_monthly[['date', '승하차인원수']],
        df_monthly_rev[['date', '당월_매출_금액']],
        on='date', how='inner'
    )
    if not merged_month.empty and not merged_month['당월_매출_금액'].isnull().all():
        p = merged_month['승하차인원수'].corr(merged_month['당월_매출_금액'])
        if not pd.isna(p):
            pearson_list.append(p)
if len(pearson_list) > 0:
    global_pearson = np.mean(pearson_list)
    global_pearson_text = f"전체 역 평균 피어슨 상관계수: {global_pearson:.3f}"
else:
    global_pearson_text = "전체 역 평균 피어슨 상관계수: 계산 불가"

# 사이드바 HTML 생성
html_sidebar = f'''
<div style="position:absolute; bottom:10px; right:10px; 
            background:white; padding:10px; border:1px solid gray; 
            border-radius:5px; font-family:{font_name}; 
            box-shadow:2px 2px 6px rgba(0,0,0,0.3); z-index:9999; width:300px;">
  <div style='margin-bottom:10px; color:#555; font-size:14px; text-align:center;'><b>{global_pearson_text}</b></div>
  <b>증가율 TOP3</b><br>'''
  
for _, r in top_inc.iterrows():
    html_sidebar += f"<a href='#' onclick=\"focusStation('{r['고유역번호']}');return false;\">{r['역명']}</a><br>"
html_sidebar += '<br><b>감소율 TOP3</b><br>'
for _, r in top_dec.iterrows():
    html_sidebar += f"<a href='#' onclick=\"focusStation('{r['고유역번호']}');return false;\">{r['역명']}</a><br>"
html_sidebar += '</div>'

# JavaScript 삽입: focusStation 함수 및 마커 맵핑
js_script = '<script>\n'
js_script += '  function focusStation(id) {\n'
js_script += f'    var m = marker_map[id];\n'
js_script += f'    var obj = eval(m);\n'
js_script += f'    var ll = obj.getLatLng();\n'
js_script += f'    {map_name}.setView(ll, 13);\n'
js_script += f'    obj.openPopup();\n'
js_script += '  }\n'
js_script += '  var marker_map = {};\n'
for k, v in marker_js.items():
    js_script += f"  marker_map['{k}'] = '{v}';\n"
js_script += '</script>'

# 사이드바 및 스크립트 추가
seoul_map.get_root().html.add_child(Element(html_sidebar + js_script))

# 결과 저장
seoul_map.save(os.path.join(curDir,'seoul_subway_visualization.html'))
print("지도 생성 완료!")
