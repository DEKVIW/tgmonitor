import streamlit as st
import streamlit_authenticator as stauth
import json
import os
from datetime import datetime, timedelta
from config import settings
import logging

# 工具函数：去除重复前缀
def clean_prefix(text: str) -> str:
    """去除重复的前缀，如“描述：描述：描述内容”、“描述描述内容”都只保留一个"""
    prefixes = ["描述：", "描述", "名称：", "名称", "资源描述：", "资源描述"]
    text = text.strip()
    for prefix in prefixes:
        while text.startswith(prefix):
            text = text[len(prefix):].lstrip()
    return text

# 页面配置
st.set_page_config(
    page_title="TG频道监控",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_DATA_FILE = "users.json"

@st.cache_data(ttl=300)
def load_auth_users():
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
        else:
            users = {}
        usernames = {}
        for uname, uinfo in users.items():
            usernames[uname] = {
                "name": uinfo.get("name", uname),
                "password": uinfo["password"],
                "email": uinfo.get("email", "")
            }
        return {"usernames": usernames}
    except Exception as e:
        logger.error(f"加载用户数据失败: {e}")
        return {"usernames": {}}

def show_login_success_message():
    if st.session_state.get("show_login_success", True):
        try:
            st.toast(f"欢迎 {st.session_state.get('name')}！", icon="🎉")
        except Exception:
            st.success(f"欢迎 {st.session_state.get('name')}！")
        st.session_state["show_login_success"] = False

def init_session_state():
    if 'selected_tags' not in st.session_state:
        st.session_state['selected_tags'] = []
    if 'page_num' not in st.session_state:
        st.session_state['page_num'] = 1
    if 'search_query' not in st.session_state:
        st.session_state['search_query'] = ''
    if 'min_content_length' not in st.session_state:
        st.session_state['min_content_length'] = 0
    if 'has_links_only' not in st.session_state:
        st.session_state['has_links_only'] = False

def handle_logout(authenticator):
    st.session_state.clear()
    st.rerun()

def main():
    try:
        auth_users = load_auth_users()
        authenticator = stauth.Authenticate(
            auth_users,
            "tg_cookie",
            settings.SECRET_SALT,
            cookie_expiry_days=1
        )
        authenticator.login(location="main")
        if st.session_state.get("authentication_status"):
            show_login_success_message()
            main_app(st.session_state.get('username'), authenticator, auth_users)
        elif st.session_state.get("authentication_status") is False:
            st.error("用户名或密码错误")
        elif st.session_state.get("authentication_status") is None:
            st.warning("请输入用户名和密码")
    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        st.error("应用启动失败，请检查配置")

def main_app(username, authenticator, auth_users):
    init_session_state()
    # 合并所有自定义CSS，只插入一次
    st.markdown("""
    <style>
    .main > div { padding-top: 0rem; }
    .block-container { padding-top: 1rem; }
    .stApp > header { height: 0; }
    div[data-testid="stVerticalBlock"] > div:first-child { gap: 0; }
    .netdisk-tag {
        display: inline-block;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 15px;
        padding: 4px 12px;
        margin: 2px 4px 2px 0;
        font-size: 12px;
        font-weight: 500;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .tag-btn {
        border: 1px solid #409eff;
        border-radius: 20px;
        padding: 4px 12px;
        margin: 2px 6px 2px 0;
        font-size: 13px;
        background: #f0f9ff;
        color: #409eff;
        display: inline-block;
        transition: all 0.3s ease;
        cursor: default;
    }
    .tag-btn:hover {
        background: #409eff;
        color: white;
        transform: translateY(-1px);
    }
    .stButton > button {
        border-radius: 20px;
        border: 1px solid #409eff;
        background: white;
        color: #409eff;
        transition: all 0.3s ease;
        min-width: 80px;
        height: 38px;
        font-size: 14px;
        font-weight: 500;
    }
    .stButton > button:hover {
        background: #409eff;
        color: white;
        transform: translateY(-1px);
    }
    .stButton > button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    .logout-btn {
        background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 8px 16px;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    .logout-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    .timestamp {
        color: #007acc;
        font-weight: 500;
        font-size: 14px;
    }
    .pagination-container {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 10px;
        margin: 20px 0;
        padding: 15px;
        background: #f8f9fa;
        border-radius: 10px;
        border: 1px solid #e9ecef;
    }
    .pagination-info {
        text-align: center;
        padding: 10px;
        color: #666;
        font-size: 14px;
        background: #fff;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-top: 10px;
    }
    .stMarkdown p {
        margin-bottom: 10px !important;
    }
    label[data-testid="stWidgetLabel"]:empty,
    label[data-testid="stWidgetLabel"] > div:empty,
    label.st-emotion-cache-ue6h4q:empty {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    /* 隐藏只包含 <style> 的 stMarkdown 容器 */
    .stMarkdown:empty, .stMarkdown p:empty {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    /* 隐藏空的 flex 容器 */
    div[style*="display: flex"][style*="justify-content: center"]:empty {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    @media (max-width: 768px) {
        .netdisk-tag { font-size: 10px; padding: 2px 8px; }
        .tag-btn { font-size: 11px; padding: 4px 12px; }
    }
    div[data-testid="stElementContainer"]:has(iframe[src*="CookieManager"]),
    div[data-testid="stElementContainer"]:has(iframe[src*="autorefresh"]) {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        overflow: hidden !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("""
<style>
div[data-testid="stElementContainer"]:has(iframe[src*="CookieManager"]),
div[data-testid="stElementContainer"]:has(iframe[src*="autorefresh"]) {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    overflow: hidden !important;
}
</style>
""", unsafe_allow_html=True)
    st.markdown("""
<style>
.stMarkdown p {
    margin-bottom: 10px !important;
}
</style>
""", unsafe_allow_html=True)
    st.markdown("""
<style>
label[data-testid="stWidgetLabel"]:empty,
label[data-testid="stWidgetLabel"] > div:empty {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}
</style>
""", unsafe_allow_html=True)
    try:
        from streamlit_autorefresh import st_autorefresh
        refresh_interval = st.sidebar.slider("🔄 自动刷新间隔(秒)", 30, 300, 60, 30)
        st_autorefresh(interval=refresh_interval * 1000, key="auto_refresh")
    except Exception:
        pass
    from sqlalchemy.orm import sessionmaker
    from models import Message, engine
    @st.cache_resource(ttl=300)
    def get_sessionmaker():
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return SessionLocal
    SessionLocal = get_sessionmaker()
    st.title("📱 TG频道监控")
    render_sidebar(username, authenticator, auth_users, SessionLocal)
    render_main_content(SessionLocal)

def render_sidebar(username, authenticator, auth_users, SessionLocal):
    with st.sidebar:
        st.header("⚙️ 筛选条件")
        def on_search_change():
            st.session_state['page_num'] = 1
        search_query = st.text_input(
            "🔍 搜索",
            value=st.session_state.get('search_query', ''),
            key="search_query",
            help="支持多关键词搜索，用空格分隔",
            on_change=on_search_change
        )
        render_tag_selector(SessionLocal)
        netdisk_types = [
            '夸克网盘', '阿里云盘', '百度网盘', '115网盘', 
            '天翼云盘', '123云盘', 'UC网盘', '迅雷网盘'
        ]
        st.multiselect(
            "💾 网盘类型",
            netdisk_types,
            default=st.session_state.get('selected_netdisks', []),
            key="selected_netdisks",
            help="选择网盘类型进行筛选"
        )
        def on_time_range_change():
            st.session_state['page_num'] = 1
        st.selectbox(
            "⏰ 时间范围",
            ["最近1小时", "最近24小时", "最近7天", "最近30天", "全部"],
            index=["最近1小时", "最近24小时", "最近7天", "最近30天", "全部"].index(st.session_state.get('time_range', '最近24小时')),
            key="time_range",
            help="筛选消息的时间范围",
            on_change=on_time_range_change
        )
        # 只用selectbox控件管理page_size，不再手动赋值
        page_size_default = st.session_state.get('page_size', 100)
        if page_size_default not in [50, 100, 200]:
            page_size_default = 100
        st.selectbox(
            "📋 每页显示",
            [50, 100, 200],
            index=[50, 100, 200].index(page_size_default),
            key="page_size",
            help="选择每页显示的消息条数"
        )
        # 移除 st.session_state.update 的同步逻辑
        st.divider()
        show_statistics(SessionLocal)
        st.divider()
        user_info = auth_users["usernames"].get(username, {})
        st.markdown(f"**👤 用户:** {user_info.get('name', username)}")
        if st.button("🚪 登出", key="sidebar_logout", use_container_width=True):
            handle_logout(authenticator)

def render_tag_selector(SessionLocal):
    def on_tag_change():
        tag_map = st.session_state.get('tag_map', {})
        st.session_state['selected_tags'] = [
            tag_map[label] for label in st.session_state.get('tag_multiselect', [])
        ]
    from sqlalchemy.sql import text
    @st.cache_data(ttl=300)
    def get_tag_stats():
        with SessionLocal() as session:
            result = session.execute(text("""
                SELECT unnest(tags) as tag, COUNT(*) as count 
                FROM messages 
                WHERE tags IS NOT NULL AND array_length(tags, 1) > 0
                GROUP BY tag 
                ORDER BY count DESC
                LIMIT 50
            """)).all()
            return [(tag, count) for tag, count in result]
    try:
        tag_items = get_tag_stats()
        tag_options = [f"{tag} ({count})" for tag, count in tag_items]
        tag_map = {f"{tag} ({count})": tag for tag, count in tag_items}
        st.session_state['tag_map'] = tag_map
        selected_tag_labels = st.multiselect(
            "🏷️ 标签",
            tag_options,
            default=[f"{tag} ({count})" for tag, count in tag_items 
                    if tag in st.session_state['selected_tags']],
            key="tag_multiselect",
            on_change=on_tag_change,
            help="选择标签进行筛选"
        )
    except Exception as e:
        logger.error(f"获取标签统计失败: {e}")
        st.error("标签加载失败")

def show_statistics(SessionLocal):
    import pandas as pd
    import altair as alt
    from sqlalchemy import func
    from models import Message
    @st.cache_data(ttl=300)
    def get_stats():
        with SessionLocal() as session:
            total = session.query(Message).count()
            today = session.query(Message).filter(
                Message.timestamp >= datetime.now().replace(hour=0, minute=0, second=0)
            ).count()
            total_links = 0
            for msg in session.query(Message).filter(Message.links.isnot(None)):
                if isinstance(msg.links, dict):
                    total_links += len(msg.links)
            days = [datetime.now().date() - timedelta(days=i) for i in range(9, -1, -1)]
            day_counts = []
            link_counts = []
            for day in days:
                next_day = day + timedelta(days=1)
                msgs = session.query(Message).filter(
                    Message.timestamp >= datetime.combine(day, datetime.min.time()),
                    Message.timestamp < datetime.combine(next_day, datetime.min.time())
                ).all()
                day_counts.append(len(msgs))
                link_counts.append(sum(len(m.links) for m in msgs if isinstance(m.links, dict)))
            return total, today, total_links, days, day_counts, link_counts
    def metric_card(title, value, icon="📄", color="#409eff"):
        st.markdown(f"""
        <div style="
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.07);
            padding: 18px 0 10px 0;
            margin-bottom: 18px;
            text-align: center;
            border: 1px solid #f0f0f0;
            width: 100%;
        ">
            <div style="font-size:18px;color:#888;margin-bottom:6px;">
                <span style="font-size:1.3em;vertical-align:middle;">{icon}</span>
                <span style="margin-left:4px;">{title}</span>
            </div>
            <div style="font-size:2.3rem;font-weight:bold;color:{color};letter-spacing:1px;">{value:,}</div>
        </div>
        """, unsafe_allow_html=True)
    try:
        total, today, total_links, days, day_counts, link_counts = get_stats()
        st.markdown("### 📊 统计信息")
        metric_card("总消息数", total, "📄", "#409eff")
        metric_card("今日消息", today, "📅", "#52c41a")
        metric_card("总链接数", total_links, "🔗", "#faad14")
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📈 最近10天消息与链接趋势")
        df = pd.DataFrame({
            "日期": [d.strftime("%m-%d") for d in days],
            "消息数": day_counts,
            "链接数": link_counts
        })
        df = df.melt("日期", var_name="类型", value_name="数量")
        # 自动修复图表数据的NaN、inf、-inf问题
        import numpy as np
        df["数量"] = df["数量"].replace([np.inf, -np.inf], 0)
        df["数量"] = df["数量"].fillna(0)
        chart = alt.Chart(df).mark_line(point=True, strokeWidth=3).encode(
            x=alt.X("日期:N", axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("数量:Q", title="数量"),
            color=alt.Color(
                "类型:N",
                legend=alt.Legend(title=None, orient="bottom", direction="horizontal"),
                scale=alt.Scale(domain=["消息数", "链接数"], range=["#409eff", "#faad14"])
            ),
            tooltip=["日期", "类型", "数量"]
        ).properties(
            width=340, height=320
        ).configure_axis(
            labelFontSize=13,
            titleFontSize=15,
            labelColor="#222",
            titleColor="#222",
            gridColor="#bbb",
            domain=True,
            domainColor="#888",
            domainWidth=1.5,
            tickColor="#888"
        ).configure_legend(
            labelFontSize=13,
            titleFontSize=15
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception as e:
        st.error(f"统计信息获取失败: {e}")

def render_main_content(SessionLocal):
    PAGE_SIZE = st.session_state['page_size']
    from sqlalchemy import or_, func
    from models import Message
    @st.cache_data(ttl=60)
    def get_filtered_messages(search_query, time_range, selected_tags, selected_netdisks, 
                            min_content_length, has_links_only, page_num, page_size):
        with SessionLocal() as db:
            query = db.query(Message)
            if search_query:
                search_terms = [term.strip() for term in search_query.split() if term.strip()]
                if search_terms:
                    search_filters = []
                    for term in search_terms:
                        search_filters.extend([
                            Message.title.ilike(f'%{term}%'),
                            Message.description.ilike(f'%{term}%')
                        ])
                    query = query.filter(or_(*search_filters))
            time_deltas = {
                "最近1小时": timedelta(hours=1),
                "最近24小时": timedelta(days=1),
                "最近7天": timedelta(days=7),
                "最近30天": timedelta(days=30)
            }
            if time_range in time_deltas:
                query = query.filter(Message.timestamp >= datetime.now() - time_deltas[time_range])
            if selected_tags:
                filters = [Message.tags.any(tag) for tag in selected_tags]
                query = query.filter(or_(*filters))
            if selected_netdisks:
                filters = [Message.netdisk_types.op('@>')(json.dumps([nd])) for nd in selected_netdisks]
                query = query.filter(or_(*filters))
            if min_content_length > 0:
                query = query.filter(
                    (func.length(Message.title) + func.length(Message.description)) >= min_content_length
                )
            if has_links_only:
                query = query.filter(Message.links.isnot(None))
            total_count = query.count()
            max_page = (total_count + page_size - 1) // page_size if total_count > 0 else 1
            if page_num > max_page and max_page > 0:
                page_num = 1
            start_idx = (page_num - 1) * page_size
            messages_page = query.order_by(Message.timestamp.desc()).offset(start_idx).limit(page_size).all()
            return messages_page, total_count, max_page
    messages_page, total_count, max_page = get_filtered_messages(
        st.session_state.get('search_query', ''),
        st.session_state.get('time_range', '最近24小时'),
        st.session_state.get('selected_tags', []),
        st.session_state.get('selected_netdisks', []),
        st.session_state.get('min_content_length', 0),
        st.session_state.get('has_links_only', False),
        st.session_state.get('page_num', 1),
        PAGE_SIZE
    )
    if total_count > 0:
        st.info(f"共找到 {total_count} 条消息")
    else:
        st.warning("没有找到匹配的消息")
        return
    render_messages(messages_page)
    render_pagination(total_count, max_page, PAGE_SIZE)

def render_messages(messages):
    for idx, msg in enumerate(messages):
        netdisk_tags = ""
        if msg.links:
            netdisk_tags = " ".join([f"💾{name}" for name in msg.links.keys()])
        
        # 多种时间格式选择，让时间更醒目
        now = datetime.now()
        msg_time = msg.timestamp
        
        # 计算时间差
        time_diff = now - msg_time
        
        if time_diff.days == 0:
            # 今天的消息
            if time_diff.seconds < 3600:  # 1小时内
                minutes = time_diff.seconds // 60
                if minutes < 1:
                    time_str = "🔥刚刚"
                else:
                    time_str = f"🔥{minutes}分钟前"
            else:
                time_str = f"⏰今天{msg_time.strftime('%H:%M')}"
        elif time_diff.days == 1:
            # 昨天的消息
            time_str = f"📅昨天{msg_time.strftime('%H:%M')}"
        elif time_diff.days < 7:
            # 一周内
            weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            weekday = weekdays[msg_time.weekday()]
            time_str = f"📆{weekday}{msg_time.strftime('%H:%M')}"
        else:
            # 更早的消息
            time_str = f"📋{msg_time.strftime('%m-%d %H:%M')}"
        
        # 简单的标题，使用醒目的时间格式
        expander_title = f"**{msg.title}** | {time_str} {netdisk_tags}"
        
        with st.expander(expander_title, expanded=False):
            # 在expander内部显示详细的带颜色时间
            detailed_time = msg_time.strftime('%Y年%m月%d日 %H:%M:%S')
            st.markdown(f"<div style='color: #007acc; font-weight: 500; margin-bottom: 8px;'>🕒 详细时间: {detailed_time}</div>", unsafe_allow_html=True)
            # 描述（加图标并去重“描述：”前缀）
            if msg.description:
                desc = clean_prefix(msg.description)
                st.markdown(f"📝 <b>描述：</b>{desc}", unsafe_allow_html=True)
            if msg.links:
                # 下载链接按钮与描述同行显示，字体更清晰
                link_buttons = []
                for name, link in msg.links.items():
                    link_buttons.append(
                        f"<a href='{link}' target='_blank' class='netdisk-tag' style='font-size:13px;font-weight:bold;color:#fff;text-decoration:none;margin-right:8px;'>{name}</a>"
                    )
                st.markdown(
                    f"<div style='display:flex;align-items:center;flex-wrap:wrap;'>"
                    f"<span style='margin-right:12px;'><b>🔗 下载链接:</b></span>"
                    + " ".join(link_buttons) +
                    "</div>", unsafe_allow_html=True)
            if msg.tags:
                # 标签与下载按钮同行显示
                tag_html = "".join([f"<span class='tag-btn' style='margin-right:6px;'>#{tag}</span>" for tag in msg.tags])
                st.markdown(
                    f"<div style='display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:10px;'>"
                    f"<b>🏷️ 标签:</b> {tag_html}"
                    "</div>", unsafe_allow_html=True)
            # 注释掉ID和频道
            # col1, col2 = st.columns(2)
            # with col1:
            #     st.caption(f"ID: {msg.id}")
            # with col2:
            #     st.caption(f"频道: {getattr(msg, 'channel_name', 'Unknown')}")

def render_pagination(total_count, max_page, PAGE_SIZE):
    if max_page <= 1:
        return
    # 只保留一个输入框列，居中显示，避免多余的markdown容器
    with st.container():
        new_page = st.number_input(
            "",
            min_value=1,
            max_value=max_page,
            value=st.session_state['page_num'],
            key="page_input"
        )
        if new_page != st.session_state['page_num']:
            st.session_state['page_num'] = new_page
            st.rerun()
    # 分页信息显示区域
    st.markdown(
        f"""
        <div class='pagination-info'>
            📄 第 <strong>{st.session_state['page_num']}</strong> 页 / 共 <strong>{max_page}</strong> 页 
            &nbsp;|&nbsp; 📊 共 <strong>{total_count}</strong> 条记录
            &nbsp;|&nbsp; 📋 每页显示 <strong>{PAGE_SIZE}</strong> 条
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()