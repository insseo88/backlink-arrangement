# Live_Dashboard.py

import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

# --- 辅助函数 (保持不变) ---
def format_days_to_years_days(days):
    if days is None or pd.isna(days): return "N/A"
    try:
        days = int(days); years = days // 365; remaining_days = days % 365
        if years > 0: return f"{years}年, {remaining_days}天"
        return f"{remaining_days}天"
    except (ValueError, TypeError): return "N/A"

# --- 页面配置 (保持不变) ---
st.set_page_config(page_title="实时数据洞察", page_icon="🏠", layout="wide")

# --- Supabase 客户端 (保持不变) ---
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 页面标题 (保持不变) ---
st.title("🏠 实时数据洞察 (Live Dashboard)")
#st.markdown("概览当前的域名资源和报价机会。")

# --- 数据加载函数 (保持不变) ---
@st.cache_data(ttl=600)
def load_live_data():
    domains_response = supabase.table('referring_domains').select('id, domain_name, da, dr, organic_traffic, age_in_days').execute()
    domains_df = pd.DataFrame(domains_response.data) if domains_response.data else pd.DataFrame()
    offers_response = supabase.table('vendor_offers').select('id, price, vendor_id, rd_id, vendors(name)').execute()
    offers_df = pd.DataFrame(offers_response.data) if offers_response.data else pd.DataFrame()
    vendors_response = supabase.table('vendors').select('id, name').execute()
    vendors_df = pd.DataFrame(vendors_response.data) if vendors_response.data else pd.DataFrame()
    return domains_df, offers_df, vendors_df

# --- 主逻辑 ---
with st.spinner("正在加载实时数据..."):
    original_domains_df, original_offers_df, original_vendors_df = load_live_data()

if original_domains_df.empty and original_offers_df.empty:
    st.warning("数据库中尚无数据。请先前往“数据管理中心”上传您的报价单。")
else:
    st.header("⚙️ 全局过滤器")
    vendor_list = sorted(original_vendors_df['name'].unique().tolist())
    selected_vendors = st.multiselect("按供应商筛选 (可多选):", options=vendor_list, help="选择一个或多个供应商来聚焦分析。如果留空，则显示全部数据。")

    if selected_vendors:
        # ✨ 核心修复: 在筛选后立即使用 .copy()
        offers_df = original_offers_df[original_offers_df['vendors'].apply(lambda x: x['name'] if isinstance(x, dict) else '').isin(selected_vendors)].copy()
        relevant_domain_ids = offers_df['rd_id'].unique()
        domains_df = original_domains_df[original_domains_df['id'].isin(relevant_domain_ids)].copy()
        vendors_df = original_vendors_df[original_vendors_df['name'].isin(selected_vendors)].copy()
    else:
        domains_df = original_domains_df.copy()
        offers_df = original_offers_df.copy()
        vendors_df = original_vendors_df.copy()
    
    st.markdown("---")

    st.header("核心指标概览")
    total_vendors = len(vendors_df)
    total_domains = len(domains_df)
    total_offers = len(offers_df)
    avg_price = offers_df['price'].mean() if not offers_df.empty else 0
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("供应商总数", f"{total_vendors}")
    col2.metric("域名池总数", f"{total_domains}")
    col3.metric("总报价机会", f"{total_offers}")
    col4.metric("平均报价", f"${avg_price:,.2f}")
    st.markdown("---")

    st.header("🔍 交互式域名浏览器")
    domain_list = [""] + sorted(domains_df['domain_name'].unique().tolist())
    selected_domain = st.selectbox("输入或选择一个域名进行查询:", domain_list)

    if selected_domain:
        domain_details = domains_df[domains_df['domain_name'] == selected_domain].iloc[0]
        st.subheader(f"指标详情: `{domain_details['domain_name']}`")
        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("DA", f"{domain_details.get('da', 'N/A')}")
        metric2.metric("DR", f"{domain_details.get('dr', 'N/A')}")
        traffic_value = domain_details.get('organic_traffic')
        metric3.metric("流量", f"{int(traffic_value):,}" if pd.notna(traffic_value) else "N/A")
        age_value = domain_details.get('age_in_days')
        metric4.metric("年龄", format_days_to_years_days(age_value))

        # ✨ 核心修复 1: 在筛选后立即使用 .copy()
        offers_for_domain = offers_df[offers_df['rd_id'] == domain_details['id']].copy()
        
        if not offers_for_domain.empty:
            # 现在可以安全地添加新列
            offers_for_domain['vendor_name'] = offers_for_domain['vendors'].apply(lambda x: x['name'] if isinstance(x, dict) else '未知')
            st.write("**供应商报价列表:**")
            st.dataframe(offers_for_domain[['vendor_name', 'price']].rename(columns={'vendor_name': '供应商', 'price': '报价 ($)'}).sort_values('报价 ($)'), width='stretch')
        else:
            st.info("该域名当前没有供应商提供报价。")

    st.markdown("---")

    st.header("📊 数据分布可视化")
    # ✨ 核心修复: 使用 .loc 避免在副本上操作
    domains_df.loc[:, 'da'] = pd.to_numeric(domains_df['da'], errors='coerce')
    domains_df.loc[:, 'dr'] = pd.to_numeric(domains_df['dr'], errors='coerce')
    offers_df.loc[:, 'price'] = pd.to_numeric(offers_df['price'], errors='coerce')

    viz_col1, viz_col2 = st.columns(2)
    with viz_col1:
        fig_da = px.histogram(domains_df.dropna(subset=['da']), x='da', title='域名池 DA 分布', nbins=20)
        st.plotly_chart(fig_da, width='stretch')
    with viz_col2:
        fig_dr = px.histogram(domains_df.dropna(subset=['dr']), x='dr', title='域名池 DR 分布', nbins=20, color_discrete_sequence=['indianred'])
        st.plotly_chart(fig_dr, width='stretch')

    fig_price = px.histogram(offers_df.dropna(subset=['price']), x='price', title='报价价格分布', nbins=30, color_discrete_sequence=['green'])
    st.plotly_chart(fig_price, width='stretch')
    st.markdown("---")

    st.header("🏆 供应商排行榜")
    if not offers_df.empty and not vendors_df.empty:
        # ✨ 核心修复 2: 使用 .loc 安全地添加新列
        offers_df.loc[:, 'vendor_name'] = offers_df['vendors'].apply(lambda x: x['name'] if isinstance(x, dict) else '未知')
        vendor_stats = offers_df['vendor_name'].value_counts().reset_index()
        vendor_stats.columns = ['供应商', '域名报价数']
        fig_vendor = px.bar(vendor_stats.head(10), x='供应商', y='域名报价数', title='Top 10 域名报价数量供应商', text='域名报价数').update_xaxes(categoryorder="total descending")
        st.plotly_chart(fig_vendor, width='stretch')

    st.header("🥇 供应商独家资源榜")
    if not original_offers_df.empty:
        domain_vendor_counts = original_offers_df.groupby('rd_id')['vendor_id'].nunique().reset_index()
        domain_vendor_counts.rename(columns={'vendor_id': 'vendor_count'}, inplace=True)
        exclusive_domain_ids = domain_vendor_counts[domain_vendor_counts['vendor_count'] == 1]['rd_id']
        
        # ✨ 核心修复 3: 在筛选后立即使用 .copy()
        exclusive_offers_df = original_offers_df[original_offers_df['rd_id'].isin(exclusive_domain_ids)].copy()
        
        if not exclusive_offers_df.empty:
            # 现在可以安全地添加新列
            exclusive_offers_df['vendor_name'] = exclusive_offers_df['vendors'].apply(lambda x: x['name'] if isinstance(x, dict) else '未知')
            exclusive_vendor_stats = exclusive_offers_df['vendor_name'].value_counts().reset_index()
            exclusive_vendor_stats.columns = ['供应商', '独家域名数']
            fig_exclusive = px.bar(exclusive_vendor_stats.head(10), x='供应商', y='独家域名数', title='Top 10 独家域名数量供应商', text='独家域名数', color_discrete_sequence=['goldenrod']).update_xaxes(categoryorder="total descending")
            st.plotly_chart(fig_exclusive, width='stretch')
        else:
            st.info("目前没有发现任何独家域名资源。")
