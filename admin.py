import streamlit as st
from sqlalchemy.orm import Session
from models import Credential, Channel, engine

st.set_page_config(page_title="后台管理", page_icon="🔧", layout="wide")
st.title("后台管理")

# API凭据管理
st.header("API凭据管理")
with Session(engine) as session:
    creds = session.query(Credential).all()
    for cred in creds:
        col1, col2, col3 = st.columns([3, 5, 2])
        col1.write(f"api_id: {cred.api_id}")
        col2.write(f"api_hash: {cred.api_hash}")
        if col3.button(f"删除", key=f"del_cred_{cred.id}"):
            session.delete(cred)
            session.commit()
            st.rerun()
    st.markdown("---")
    with st.form("add_cred_form"):
        api_id = st.text_input("新API ID")
        api_hash = st.text_input("新API Hash")
        submitted = st.form_submit_button("添加API凭据")
        if submitted and api_id and api_hash:
            session.add(Credential(api_id=api_id, api_hash=api_hash))
            session.commit()
            st.success("添加成功！")
            st.rerun()

# 频道管理
st.header("监听频道管理")
with Session(engine) as session:
    chans = session.query(Channel).all()
    for chan in chans:
        col1, col2 = st.columns([6, 2])
        col1.write(f"频道: {chan.username}")
        if col2.button(f"删除", key=f"del_chan_{chan.id}"):
            session.delete(chan)
            session.commit()
            st.rerun()
    st.markdown("---")
    with st.form("add_chan_form"):
        username = st.text_input("新频道用户名（不加@）")
        submitted = st.form_submit_button("添加频道")
        if submitted and username:
            session.add(Channel(username=username))
            session.commit()
            st.success("添加成功！")
            st.rerun() 