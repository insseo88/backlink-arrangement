# pages/4_Shopping_Cart.py (V7.3 - 最终修复版：修正时区和Project ID)

import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import numpy as np
import re

# --- 配置 ---
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

INDEXCHECKR_API_KEY = st.secrets.get("indexcheckr_api_key")
# ✨✨✨ 核心修正 1：确保使用正确的 Project ID ✨✨✨
INDEXCHECKR_PROJECT_ID = st.secrets.get("indexcheckr_project_id")

@st.cache_resource
def get_requests_session_with_retry():
    session = requests.Session()
    retry_strategy = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["HEAD", "GET", "POST", "PUT"])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter )
    session.mount("https://", adapter )
    return session

# --- 辅助函数 ---
def format_days_to_years_days(days):
    if days is None or pd.isna(days): return "N/A"
    try:
        days = int(days); years = days // 365; remaining_days = days % 365
        return f"{years}年, {remaining_days}天" if years > 0 else f"{remaining_days}天"
    except (ValueError, TypeError): return "N/A"

def calculate_unified_age(row):
    if pd.notna(row.get('vendor_offers_referring_domains_first_seen_date')):
        try:
            seen_date = pd.to_datetime(row['vendor_offers_referring_domains_first_seen_date'])
            now_date = pd.Timestamp.now(tz='UTC')
            if seen_date.tzinfo is None: seen_date = seen_date.tz_localize('UTC')
            return (now_date - seen_date).days
        except (ValueError, TypeError): pass
    if pd.notna(row.get('vendor_offers_referring_domains_age_in_days')):
        try: return int(row['vendor_offers_referring_domains_age_in_days'])
        except (ValueError, TypeError): pass
    return None

# ✨✨✨ 核心修正 2：修复日期格式化函数 ✨✨✨
def format_check_date(date_str):
    if not date_str or pd.isna(date_str): return "从未"
    try:
        # API返回的已经是带有时区信息的字符串，直接解析
        if isinstance(date_str, str):
            dt_object = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # 如果是Pandas的Timestamp对象，它可能已经有时区
        elif isinstance(date_str, pd.Timestamp):
            dt_object = date_str.to_pydatetime()
        else: # 其他意外情况
            return "日期无效"

        # 确保对象有时区，如果没有，则假定为UTC（作为安全兜底）
        if dt_object.tzinfo is None:
            dt_object = dt_object.replace(tzinfo=timezone.utc)

        # 转换为GMT+8
        gmt8_tz = timezone(timedelta(hours=8))
        gmt8_dt = dt_object.astimezone(gmt8_tz)
        return gmt8_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return "日期格式错误"


# --- 域名收录检查函数 ---
def get_api_headers():
    return {"Accept": "application/json", "Content-Type": "application/json", "X-AUTH-TOKEN": INDEXCHECKR_API_KEY}

def get_single_domain_status_with_retry(domain, headers):
    session = get_requests_session_with_retry()
    url_to_check = f"https://{domain}"
    try:
        api_url_get = f"https://indexcheckr.com/api/v1/project/{INDEXCHECKR_PROJECT_ID}/pages"
        response = session.get(api_url_get, headers=headers, params={'url': url_to_check}, timeout=30 )
        if response.ok:
            pages_status = response.json().get('data', [])
            if pages_status:
                page_data = pages_status[0]
                if page_data.get('status') == 'being_processed':
                    time.sleep(5)
                    response_retry = session.get(api_url_get, headers=headers, params={'url': url_to_check}, timeout=30)
                    if response_retry.ok:
                        pages_status_retry = response_retry.json().get('data', [])
                        if pages_status_retry: return pages_status_retry[0]
                return page_data
    except requests.RequestException: return None
    return None

def format_index_status(status):
    if pd.isna(status) or status is None: return '未检查'
    if status == "page_indexed": return f"✅ 已收录"
    if status == "page_not_indexed": return f"❌ 未收录"
    return f"🔄 {status}"

# --- HTTP 状态检查函数 ---
def get_core_domain(url):
    if not isinstance(url, str): return ""
    no_protocol = re.sub(r'^https?:\/\/', '', url )
    domain_part = no_protocol.split('/')[0]
    no_www = re.sub(r'^www\.', '', domain_part)
    return no_www.lower()

def check_http_status(domain ):
    session = get_requests_session_with_retry()
    url = f"https://{domain}" if not domain.startswith('http' ) else domain
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'}
        with session.get(url, headers=headers, timeout=45, allow_redirects=True, stream=True) as response:
            final_url = response.url
            original_core = get_core_domain(domain)
            final_core = get_core_domain(final_url)
            is_meaningful_redirect = original_core != final_core
            return {"status": str(response.status_code), "final_url": final_url if is_meaningful_redirect else "无跳转"}
    except requests.exceptions.Timeout: return {"status": "超时", "final_url": "N/A"}
    except requests.exceptions.ConnectionError: return {"status": "链接错误", "final_url": "N/A"}
    except requests.exceptions.RequestException: return {"status": "请求失败", "final_url": "N/A"}

def format_http_status(status_dict ):
    if not isinstance(status_dict, dict): return "未检查"
    status = status_dict.get("status")
    if status == '404': return f"❌ {status}"
    if status in ['超时', '链接错误', '请求失败']: return f"⚠️ {status}"
    return status

# --- Streamlit 页面布局 ---
st.set_page_config(layout="wide")
st.title("🛒 购物车与采购计划")

if 'confirm_clear_cart' not in st.session_state: st.session_state.confirm_clear_cart = False
if 'http_status_results' not in st.session_state: st.session_state.http_status_results = {}
if 'cart_index_results' not in st.session_state: st.session_state.cart_index_results = {}

@st.cache_data(ttl=30 )
def load_cart_data():
    cart_query = """
        id, website_id, client_websites (name), offer_id,
        vendor_offers (
            price, vendors (name),
            referring_domains (
                domain_name, da, dr, age_in_days, first_seen_date, organic_traffic
            )
        )
    """
    response = supabase.table('shopping_cart').select(cart_query).execute()
    return pd.json_normalize(response.data, sep='_') if response.data else pd.DataFrame()

cart_df = load_cart_data()
api_configured = INDEXCHECKR_API_KEY and INDEXCHECKR_PROJECT_ID

if not api_configured:
    st.warning("警告：未在 Secrets 中配置 `indexcheckr_api_key` 和 `indexcheckr_project_id_2`。收录检查功能将不可用。")

if cart_df.empty:
    st.success("您的购物车是空的！")
else:
    cart_df['unified_age_in_days'] = cart_df.apply(calculate_unified_age, axis=1)
    cart_df['age_formatted'] = cart_df['unified_age_in_days'].apply(format_days_to_years_days)

    st.header("📊 采购计划总览")
    total_links, total_cost_usd, total_websites = len(cart_df), cart_df['vendor_offers_price'].sum(), cart_df['client_websites_name'].nunique()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("网站总数", f"{total_websites} 个"); col2.metric("链接总数", f"{total_links} 个")
    col3.metric("预估总花费 (USD)", f"$ {total_cost_usd:,.2f}"); col4.metric("预估总花费 (RM)", f"RM {total_cost_usd * 5:,.2f}")
    st.markdown("##### 按网站汇总")
    summary_df = cart_df.rename(columns={'client_websites_name': '网站', 'vendor_offers_price': '价格'})
    website_summary = summary_df.groupby('网站').agg(链接数=('价格', 'count'), 预估花费_USD=('价格', 'sum')).reset_index()
    website_summary['预估花费_RM'] = website_summary['预估花费_USD'] * 5
    st.dataframe(website_summary[['网站', '链接数', '预估花费_USD', '预估花费_RM']].style.format({"预估花费_USD": "${:,.2f}", "预估花费_RM": "RM {:,.2f}"}), width='stretch')

    st.markdown("---")
    st.header("📑 采购详情与操作")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("🚦 检查所有外链域名的 HTTP 状态", type="secondary", use_container_width=True):
            all_domains_in_cart = cart_df['vendor_offers_referring_domains_domain_name'].unique()
            total_domains = len(all_domains_in_cart)
            progress_bar = st.progress(0, text=f"准备开始检查 {total_domains} 个链接...")
            for i, domain in enumerate(all_domains_in_cart):
                progress_bar.progress((i + 1) / total_domains, text=f"正在检查: {domain} ({i+1}/{total_domains})")
                status_dict = check_http_status(domain )
                st.session_state.http_status_results[domain] = status_dict
                time.sleep(0.1 )
            progress_bar.empty()
            st.success(f"✅ 所有 {total_domains} 个链接状态检查完成！")
            st.rerun()
    
    with btn_col2:
        if st.button("🔍 临时检查所有域名的收录状态", type="secondary", use_container_width=True, disabled=not api_configured):
            all_domains_in_cart = cart_df['vendor_offers_referring_domains_domain_name'].unique().tolist()
            with st.spinner("正在向 IndexCheckr 平台提交所有域名..."):
                session = get_requests_session_with_retry()
                for domain in all_domains_in_cart:
                    payload = {"url": f"https://{domain}", "checkPeriod": "none", "stopCheckWhenIndexed": True}
                    try:
                        session.post(f"https://indexcheckr.com/api/v1/project/{INDEXCHECKR_PROJECT_ID}/pages", headers=get_api_headers( ), json=payload, timeout=30)
                    except requests.RequestException: pass
                    time.sleep(0.5)
            
            with st.spinner("提交完成，等待10秒后开始获取最新状态..."):
                time.sleep(10)

            total_domains = len(all_domains_in_cart)
            progress_bar = st.progress(0, text=f"准备开始获取 {total_domains} 个域名的状态...")
            headers_get = get_api_headers()
            for i, domain in enumerate(all_domains_in_cart):
                progress_bar.progress((i + 1) / total_domains, text=f"正在获取: {domain} ({i+1}/{total_domains})")
                page_data = get_single_domain_status_with_retry(domain, headers_get)
                if page_data:
                    last_check_obj = page_data.get('lastCheckAt')
                    last_check_date = last_check_obj.get('date') if last_check_obj else None
                    st.session_state.cart_index_results[domain] = {
                        'status': page_data.get('status'),
                        'lastCheckAt': last_check_date
                    }
                time.sleep(0.5)
            
            progress_bar.empty()
            st.success(f"✅ 所有 {total_domains} 个域名临时检查完成！")
            st.rerun()

    display_columns = {
        'client_websites_name': '目标网站', 'vendor_offers_referring_domains_domain_name': '外链域名',
        'vendor_offers_price': '价格', 'vendor_offers_vendors_name': '供应商',
        'vendor_offers_referring_domains_da': 'DA', 'vendor_offers_referring_domains_dr': 'DR',
        'vendor_offers_referring_domains_organic_traffic': '流量', 'age_formatted': '年龄'
    }
    display_df = cart_df[display_columns.keys()].rename(columns=display_columns)
    
    temp_status_map = display_df['外链域名'].map(st.session_state.cart_index_results).fillna({})
    display_df['域名收录'] = temp_status_map.apply(lambda x: x.get('status') if isinstance(x, dict) else None).apply(format_index_status)
    display_df['最后检查于 (GMT+8)'] = temp_status_map.apply(lambda x: x.get('lastCheckAt') if isinstance(x, dict) else None).apply(format_check_date)
    
    http_status_map = display_df['外链域名'].map(st.session_state.http_status_results )
    display_df['HTTP 状态'] = http_status_map.apply(format_http_status )
    display_df['最终链接'] = http_status_map.apply(lambda x: x.get('final_url' ) if isinstance(x, dict) else "未检查")
    
    display_df.insert(0, "勾选操作", False)
    final_columns = ["勾选操作", "目标网站", "外链域名", "HTTP 状态", "最终链接", "域名收录", "最后检查于 (GMT+8)", "价格", "供应商", "DA", "DR", "流量", "年龄"]
    display_df = display_df[final_columns]
    
    edited_df = st.data_editor(
        display_df,
        column_config={
            "勾选操作": st.column_config.CheckboxColumn("勾选操作", default=False),
            "价格": st.column_config.NumberColumn(format="$%.2f"), "流量": st.column_config.NumberColumn(format="%d"),
            "最终链接": st.column_config.LinkColumn("最终链接", help="点击跳转到最终跳转的页面", width="medium")
        },
        disabled=display_df.columns.drop("勾选操作"), hide_index=True, width='stretch', key="unified_cart_editor"
    )
    
    selected_rows = edited_df[edited_df['勾选操作']]
    if not selected_rows.empty:
        original_indices = cart_df.index[selected_rows.index]
        st.markdown("---")
        st.subheader("对勾选的项目执行操作")
        
        if st.button(f"❌ 从购物车移除选中的 {len(original_indices)} 个项目", type="primary"):
            with st.spinner("正在移除..."):
                cart_ids_to_remove = cart_df.loc[original_indices, 'id'].tolist()
                supabase.table('shopping_cart').delete().in_('id', [int(i) for i in cart_ids_to_remove]).execute()
            st.success("成功移除所选项目。"); st.cache_data.clear(); st.rerun()

    # --- 确认采购并写入 purchase_history ---
    st.markdown("---")
    st.header("✅ 确认采购")
    st.info("点击下方按钮，将购物车中的所有项目标记为“已购买”，并记录到采购历史中。此操作会清空购物车。")

    if st.button(f"确认采购全部 {len(cart_df)} 个项目并生成历史记录", type="primary", use_container_width=True):
        with st.spinner("正在处理采购记录..."):
            purchase_time = datetime.now(timezone.utc).isoformat()
            records_to_insert = []
            for _, row in cart_df.iterrows():
                records_to_insert.append({
                    'purchase_date': purchase_time, 'actual_cost': row['vendor_offers_price'],
                    'live_link': None, 'domain_name_text': row['vendor_offers_referring_domains_domain_name'],
                    'vendor_name_text': row['vendor_offers_vendors_name'], 'website_name_text': row['client_websites_name'],
                    'website_id': row['website_id'], 'offer_id': row['offer_id']
                })
            
            supabase.table('purchase_history').insert(records_to_insert).execute()
            supabase.table('shopping_cart').delete().neq('id', -1).execute()

        st.success(f"采购成功！已生成 {len(records_to_insert)} 条历史记录，并清空购物车。")
        st.balloons()
        st.cache_data.clear()
        st.session_state.http_status_results.clear( )
        st.session_state.cart_index_results.clear()
        st.rerun()

    # --- 危险操作区 ---
    st.markdown("---")
    with st.container(border=True):
        st.subheader("⚠️ 危险操作区")
        if not st.session_state.confirm_clear_cart:
            if st.button("🗑️ 清空整个购物车"):
                st.session_state.confirm_clear_cart = True; st.rerun()
        else:
            st.warning("**您确定要清空整个购物车吗？此操作不可撤销！**")
            col1, col2, _ = st.columns([1, 1, 4])
            if col1.button("✅ 是，确认清空", type="primary"):
                with st.spinner("正在清空购物车..."):
                    supabase.table('shopping_cart').delete().neq('id', -1).execute()
                st.session_state.confirm_clear_cart = False
                st.success("购物车已成功清空！")
                st.cache_data.clear()
                st.session_state.http_status_results.clear( )
                st.session_state.cart_index_results.clear()
                st.rerun()
            if col2.button("❌ 否，我点错了"):
                st.session_state.confirm_clear_cart = False; st.rerun()
