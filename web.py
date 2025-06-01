import streamlit as st
from sqlalchemy.orm import Session
from models import Message, engine
import pandas as pd
from datetime import datetime, timedelta
from collections import Counter
from sqlalchemy import or_

# 初始化session_state用于标签筛选
if 'selected_tags' not in st.session_state:
    st.session_state['selected_tags'] = []

st.set_page_config(
    page_title="TG频道监控",
    page_icon="📱",
    layout="wide"
)

# 设置页面标题
st.title("📱 TG频道监控")

# 创建侧边栏过滤器
st.sidebar.header("筛选条件")

# 时间范围选择
time_range = st.sidebar.selectbox(
    "时间范围",
    ["最近24小时", "最近7天", "最近30天", "全部"]
)

# 标签选择（标签云，显示数量，降序）
with Session(engine) as session:
    all_tags = session.query(Message.tags).all()
    tag_list = [tag for tags in all_tags for tag in (tags[0] if tags[0] else [])]
    tag_counter = Counter(tag_list)
    tag_items = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)
    tag_options = [f"{tag} ({count})" for tag, count in tag_items]
    tag_map = {f"{tag} ({count})": tag for tag, count in tag_items}
    # 默认选中session_state中的标签
    selected_tag_labels = st.sidebar.multiselect(
        "标签", tag_options,
        default=[f"{tag} ({tag_counter[tag]})" for tag in st.session_state['selected_tags'] if tag in tag_counter]
    )
    selected_tags = [tag_map[label] for label in selected_tag_labels]
    # 同步session_state
    st.session_state['selected_tags'] = selected_tags

# 网盘类型筛选
netdisk_types = ['夸克网盘', '阿里云盘', '百度网盘', '115网盘', '天翼云盘', '123云盘', 'UC网盘', '迅雷']
selected_netdisks = st.sidebar.multiselect("网盘类型", netdisk_types)

# 构建查询
with Session(engine) as session:
    query = session.query(Message)
    # 应用时间范围过滤
    if time_range == "最近24小时":
        query = query.filter(Message.timestamp >= datetime.now() - timedelta(days=1))
    elif time_range == "最近7天":
        query = query.filter(Message.timestamp >= datetime.now() - timedelta(days=7))
    elif time_range == "最近30天":
        query = query.filter(Message.timestamp >= datetime.now() - timedelta(days=30))
    # 应用标签过滤
    if selected_tags:
        filters = [Message.tags.any(tag) for tag in selected_tags]
        query = query.filter(or_(*filters))
    # 按时间倒序排序
    messages = query.order_by(Message.timestamp.desc()).all()

# 显示消息列表前，按网盘类型过滤
if selected_netdisks:
    messages = [msg for msg in messages if any(nd in (msg.links or {}) for nd in selected_netdisks)]

# 显示消息列表
for msg in messages:
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

# 处理点击条目标签筛选
if 'tag_click' in st.session_state and st.session_state['tag_click']:
    tag = st.session_state['tag_click']
    if tag not in st.session_state['selected_tags']:
        st.session_state['selected_tags'].append(tag)
        st.session_state['tag_click'] = None
        st.rerun()
    st.session_state['tag_click'] = None

# 添加自动刷新
st.empty()
st.markdown("---")
st.markdown("页面每60秒自动刷新一次")

# 添加全局CSS，强力覆盖expander内容区的gap，只保留一处，放在文件最后
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