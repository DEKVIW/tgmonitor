import streamlit as st
import hashlib
import json
import os
from datetime import datetime, timedelta

# 页面配置
st.set_page_config(
    page_title="TG频道监控",
    page_icon="📱",
    layout="wide"
)

# 简单的用户数据存储
USER_DATA_FILE = "users.json"

def load_users():
    """加载用户数据"""
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # 默认用户数据
        default_users = {
            "admin": {
                "password": hashlib.sha256("admin123".encode()).hexdigest(),
                "name": "管理员",
                "email": "admin@example.com"
            },
            "user": {
                "password": hashlib.sha256("user123".encode()).hexdigest(),
                "name": "用户",
                "email": "user@example.com"
            }
        }
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_users, f, ensure_ascii=False, indent=2)
        return default_users

def verify_password(username, password):
    """验证用户密码"""
    users = load_users()
    if username in users:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return users[username]["password"] == password_hash
    return False

def get_user_info(username):
    """获取用户信息"""
    users = load_users()
    return users.get(username, {})

def login_form():
    """显示登录表单"""
    st.title("🔐 TG频道监控 - 登录")
    # 只保留管理员登录提示
    st.info("请使用管理员账号登录")
    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submit = st.form_submit_button("登录")
        if submit:
            if username and password:
                if verify_password(username, password):
                    user_info = get_user_info(username)
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.session_state['user_info'] = user_info
                    st.session_state['login_time'] = datetime.now()
                    st.success("登录成功！")
                    st.rerun()
                else:
                    st.error("用户名或密码错误")
            else:
                st.warning("请输入用户名和密码")

def check_login_status():
    """检查登录状态"""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    
    # 检查登录是否过期（24小时）
    if st.session_state['logged_in'] and 'login_time' in st.session_state:
        login_time = st.session_state['login_time']
        if datetime.now() - login_time > timedelta(hours=24):
            st.session_state['logged_in'] = False
            st.warning("登录已过期，请重新登录")
    
    return st.session_state['logged_in']

def logout():
    """退出登录"""
    st.session_state['logged_in'] = False
    if 'username' in st.session_state:
        del st.session_state['username']
    if 'user_info' in st.session_state:
        del st.session_state['user_info']
    if 'login_time' in st.session_state:
        del st.session_state['login_time']
    st.rerun()

def main_app():
    """主应用程序"""
    # 原有的导入语句
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60_000, key="60sec")

    from sqlalchemy.orm import Session
    from models import Message, engine
    import pandas as pd
    from datetime import datetime, timedelta
    from collections import Counter
    from sqlalchemy import or_, func
    from sqlalchemy.sql import text
    from sqlalchemy.orm import sessionmaker

    # 缓存数据库 sessionmaker 工厂
    @st.cache_resource(ttl=60*5)
    def get_sessionmaker():
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return SessionLocal

    SessionLocal = get_sessionmaker()

    # 初始化session_state用于标签筛选
    if 'selected_tags' not in st.session_state:
        st.session_state['selected_tags'] = []

    # 顶部显示用户信息和登出按钮
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.title("📱 TG频道监控")
    with col2:
        user_info = st.session_state.get('user_info', {})
        st.write(f"欢迎, {user_info.get('name', st.session_state.get('username', '用户'))}")
    with col3:
        if st.button("登出"):
            logout()

    # 创建侧边栏过滤器
    st.sidebar.header("筛选条件")

    # 搜索框
    search_query = st.sidebar.text_input("搜索标题和描述", "")

    # 时间范围选择
    time_range = st.sidebar.selectbox(
        "时间范围",
        ["最近24小时", "最近7天", "最近30天", "全部"]
    )

    def on_tag_change():
        tag_map = st.session_state.get('tag_map', {})
        st.session_state['selected_tags'] = [tag_map[label] for label in st.session_state.get('tag_multiselect', [])]

    # 标签选择（标签云，显示数量，降序）
    with Session(engine) as session:
        tag_counts = session.execute(text("""
            SELECT unnest(tags) as tag, COUNT(*) as count 
            FROM messages 
            GROUP BY tag 
            ORDER BY count DESC
        """)).all()
        tag_items = [(tag, count) for tag, count in tag_counts]
        tag_options = [f"{tag} ({count})" for tag, count in tag_items]
        tag_map = {f"{tag} ({count})": tag for tag, count in tag_items}
        st.session_state['tag_map'] = tag_map
        
        selected_tag_labels = st.sidebar.multiselect(
            "标签", tag_options,
            default=[f"{tag} ({count})" for tag, count in tag_items if tag in st.session_state['selected_tags']],
            key="tag_multiselect",
            on_change=on_tag_change
        )

    # 网盘类型筛选
    netdisk_types = ['夸克网盘', '阿里云盘', '百度网盘', '115网盘', '天翼云盘', '123云盘', 'UC网盘', '迅雷']
    selected_netdisks = st.sidebar.multiselect("网盘类型", netdisk_types)

    # 分页参数
    PAGE_SIZE = 100
    if 'page_num' not in st.session_state:
        st.session_state['page_num'] = 1

    @st.cache_data(ttl=60)
    def get_filtered_messages(search_query, time_range, selected_tags, selected_netdisks, page_num):
        with SessionLocal() as db:
            query = db.query(Message)
            # 搜索条件
            if search_query:
                search_terms = search_query.split()
                search_filters = []
                for term in search_terms:
                    search_filters.append(Message.title.ilike(f'%{term}%'))
                    search_filters.append(Message.description.ilike(f'%{term}%'))
                query = query.filter(or_(*search_filters))
            # 时间范围
            if time_range == "最近24小时":
                query = query.filter(Message.timestamp >= datetime.now() - timedelta(days=1))
            elif time_range == "最近7天":
                query = query.filter(Message.timestamp >= datetime.now() - timedelta(days=7))
            elif time_range == "最近30天":
                query = query.filter(Message.timestamp >= datetime.now() - timedelta(days=30))
            # 标签过滤
            if selected_tags:
                filters = [Message.tags.any(tag) for tag in selected_tags]
                query = query.filter(or_(*filters))
            # 网盘类型过滤（数据库层面，使用原生@>操作符并手动序列化JSON）
            if selected_netdisks:
                filters = [Message.netdisk_types.op('@>')(json.dumps([nd])) for nd in selected_netdisks]
                query = query.filter(or_(*filters))
            # 总数
            total_count = query.count()
            max_page = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
            if page_num > max_page and max_page > 0:
                page_num = 1
            start_idx = (page_num - 1) * PAGE_SIZE
            messages_page = query.order_by(Message.timestamp.desc()).offset(start_idx).limit(PAGE_SIZE).all()
            return messages_page, total_count, max_page

    # 获取当前页数据
    messages_page, total_count, max_page = get_filtered_messages(
        search_query,
        time_range,
        st.session_state['selected_tags'],
        selected_netdisks,
        st.session_state['page_num']
    )

    # 显示消息列表（分页后）
    for msg in messages_page:
        # 标题行保留网盘标签，用特殊符号区分
        if msg.links:
            netdisk_tags = " ".join([f"🔵[{name}]" for name in msg.links.keys()])
        else:
            netdisk_tags = ""
        expander_title = f"{msg.title} - 🕒{msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}  {netdisk_tags}"
        with st.expander(expander_title):
            if msg.description:
                st.markdown(msg.description)
            if msg.links:
                link_str = "　".join([
                    f"<a href='{link}' target='_blank'><span class='netdisk-tag'>{name}</span></a>"
                    for name, link in msg.links.items()
                ])
                st.markdown(link_str, unsafe_allow_html=True)
            # 条目标签区（仅展示，不可点击，保留样式）
            if msg.tags:
                tag_html = ""
                for tag in msg.tags:
                    tag_html += f"<span class='tag-btn'>#{tag}</span>"
                st.markdown(tag_html, unsafe_allow_html=True)

    # 显示分页信息和跳转控件（按钮和页码信息同一行居中）
    if max_page > 1:
        col1, col2, col3 = st.columns([1,2,1])
        with col1:
            if st.button('上一页', disabled=st.session_state['page_num']==1, key='prev_page'):
                st.session_state['page_num'] = max(1, st.session_state['page_num']-1)
                st.rerun()
        with col2:
            st.markdown(f"<div style='text-align:center;line-height:38px;'>共 {total_count} 条，当前第 {st.session_state['page_num']} / {max_page} 页</div>", unsafe_allow_html=True)
        with col3:
            if st.button('下一页', disabled=st.session_state['page_num']==max_page, key='next_page'):
                st.session_state['page_num'] = min(max_page, st.session_state['page_num']+1)
                st.rerun()

    # 添加自动刷新
    st.empty()
    st.markdown("---")
    st.markdown("页面每60秒自动刷新一次")

    # 添加全局CSS
    st.markdown("""
        <style>
        [data-testid="stExpander"] [data-testid="stExpanderContent"] {
            gap: 0.2rem !important;
        }
        div[data-testid="stExpanderContent"] {
            gap: 0.2rem !important;
        }
        [data-testid="stExpander"] * {
            gap: 0.2rem !important;
        }
        .netdisk-tag {
            display: inline-block;
            background: #e6f0fa;
            color: #409eff;
            border-radius: 12px;
            padding: 2px 10px;
            margin: 2px 4px 2px 0;
            font-size: 13px;
        }
        .tag-btn {
            border:1px solid #222;
            border-radius:8px;
            padding:4px 16px;
            margin:2px 6px 2px 0;
            font-size:15px;
            background:#fff;
            color:#222;
            display:inline-block;
            transition: background 0.2s, color 0.2s;
            cursor: default;
        }
        .tag-btn:hover {
            background: #fff;
            color: #222;
        }
        </style>
    """, unsafe_allow_html=True)

# 主程序入口
def main():
    if check_login_status():
        main_app()
    else:
        login_form()

if __name__ == "__main__":
    main()