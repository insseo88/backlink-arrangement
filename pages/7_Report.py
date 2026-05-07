# pages/7_Report.py

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, date

# --- 配置 Supabase 客户端 ---
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(layout="wide")
st.title("📈 采购与质量报告")

# --- 数据加载与处理函数 ---
@st.cache_data(ttl=60)
def load_all_purchase_data():
    """从 Supabase 加载所有采购历史记录"""
    query = "id, purchase_date, actual_cost, live_link, domain_name_text, vendor_name_text, website_name_text, google_index_status, detected_anchor_text, detected_link_type, http_status"
    response = supabase.table('purchase_history' ).select(query).order('purchase_date', desc=True).execute()
    return pd.DataFrame(response.data) if response.data else pd.DataFrame()

# --- 主逻辑 ---
all_df_raw = load_all_purchase_data()

if all_df_raw.empty:
    st.info("采购历史为空，无法生成报告。")
else:
    # --- 1. 数据预处理 ---
    df = all_df_raw.copy()
    for col in ['http_status', 'google_index_status', 'detected_anchor_text', 'detected_link_type', 'actual_cost', 'vendor_name_text', 'website_name_text']:
        if col not in df.columns: df[col] = None
    df['purchase_date'] = pd.to_datetime(df['purchase_date'], dayfirst=True, errors='coerce' )
    df['采购月份'] = df['purchase_date'].dt.to_period('M').astype(str)
    df['actual_cost'] = pd.to_numeric(df['actual_cost'], errors='coerce').fillna(0)
    for col in ['vendor_name_text', 'website_name_text', 'http_status', 'google_index_status', 'detected_link_type']:
        if col in df.columns and df[col].dtype == 'object': df[col] = df[col].str.strip( )

    # --- 2. 筛选器 ---
    st.sidebar.header("报告筛选器")
    date_options = df['purchase_date'].dropna()
    start_date = date_options.min().date() if not date_options.empty else date.today()
    end_date = date_options.max().date() if not date_options.empty else date.today()
    selected_date_range = st.sidebar.date_input("按采购日期筛选", value=(start_date, end_date), min_value=start_date, max_value=end_date)
    selected_vendors = st.sidebar.multiselect("按供应商筛选", options=df['vendor_name_text'].dropna().unique())
    selected_websites = st.sidebar.multiselect("按目标网站筛选", options=df['website_name_text'].dropna().unique())

    # 应用筛选
    filtered_df = df.copy()
    if len(selected_date_range) == 2:
        start, end = pd.to_datetime(selected_date_range[0]), pd.to_datetime(selected_date_range[1])
        filtered_df = filtered_df[(filtered_df['purchase_date'] >= start) & (filtered_df['purchase_date'] <= end)]
    if selected_vendors: filtered_df = filtered_df[filtered_df['vendor_name_text'].isin(selected_vendors)]
    if selected_websites: filtered_df = filtered_df[filtered_df['website_name_text'].isin(selected_websites)]

    # --- 3. 渲染报告内容 ---
    if filtered_df.empty:
        st.warning("根据您的筛选条件，没有可用于生成报告的数据。")
    else:
        st.header("关键指标 (KPIs)")
        total_spent_usd = filtered_df['actual_cost'].sum()
        total_spent_rm = total_spent_usd * 5
        total_links = len(filtered_df)
        total_websites = filtered_df['website_name_text'].nunique()
        kpi_cols = st.columns(4)
        kpi_cols[0].metric("总花费 (USD)", f"${total_spent_usd:,.2f}")
        kpi_cols[1].metric("总花费 (RM)", f"RM {total_spent_rm:,.2f}")
        kpi_cols[2].metric("总链接数", f"{total_links} 条")
        kpi_cols[3].metric("覆盖网站数", f"{total_websites} 个")

        st.markdown("---")
        st.header("图表分析")
        monthly_analysis = filtered_df.groupby('采购月份').agg(总花费=('actual_cost', 'sum'), 网站数量=('website_name_text', 'nunique')).reset_index()
        fig_monthly = go.Figure()
        fig_monthly.add_trace(go.Bar(x=monthly_analysis['采购月份'], y=monthly_analysis['总花费'], name='每月花费', text=monthly_analysis['总花费'], texttemplate='$%{text:,.0f}', textposition='outside'))
        fig_monthly.add_trace(go.Scatter(x=monthly_analysis['采购月份'], y=monthly_analysis['网站数量'], name='覆盖网站数', mode='lines+markers', yaxis='y2'))
        fig_monthly.update_layout(title_text="每月花费 vs 网站覆盖广度", xaxis_title="月份", yaxis_title="总花费 (USD)", yaxis2=dict(title="覆盖网站数", overlaying='y', side='right'), legend=dict(x=0.01, y=0.99))
        st.plotly_chart(fig_monthly, width='stretch')
        chart_cols = st.columns(2)
        vendor_spend = filtered_df.groupby('vendor_name_text')['actual_cost'].sum().nlargest(10).reset_index()
        fig_vendor = px.pie(vendor_spend, names='vendor_name_text', values='actual_cost', title='Top 10 供应商花费占比', hole=0.4)
        chart_cols[0].plotly_chart(fig_vendor, width='stretch')
        website_spend = filtered_df.groupby('website_name_text')['actual_cost'].sum().nlargest(10).reset_index()
        fig_website = px.pie(website_spend, names='website_name_text', values='actual_cost', title='Top 10 目标网站花费占比', hole=0.4)
        chart_cols[1].plotly_chart(fig_website, width='stretch')

        # ✨ V3.6 核心修正: 供应商质量分析
        st.markdown("---")
        st.header("供应商质量与风险分析")

        vendor_summary = filtered_df.groupby('vendor_name_text').agg(
            链接数=('domain_name_text', 'count'),
            总花费=('actual_cost', 'sum')
        ).reset_index()

        # 使用 .get(key, 0) 的方式安全地获取计数值
        vendor_summary['有效链接数'] = vendor_summary['vendor_name_text'].map(filtered_df[filtered_df['http_status'].astype(str ).str.match(r'2\d{2}|3\d{2}', na=False)].groupby('vendor_name_text')['domain_name_text'].count()).fillna(0)
        vendor_summary['收录链接数'] = vendor_summary['vendor_name_text'].map(filtered_df[filtered_df['google_index_status'] == 'page_indexed'].groupby('vendor_name_text')['domain_name_text'].count()).fillna(0)
        
        # 定义 "错误交付" 的条件
        error_mask = (
            (filtered_df['detected_link_type'] == 'Nofollow') |
            (filtered_df['http_status'] == '404' ) |
            (filtered_df['detected_anchor_text'].str.contains('失败|未找到链接|超时', na=False))
        )
        vendor_summary['错误交付数'] = vendor_summary['vendor_name_text'].map(filtered_df[error_mask].groupby('vendor_name_text')['domain_name_text'].count()).fillna(0)

        # 计算比率
        vendor_summary['有效链接率 (%)'] = vendor_summary.apply(lambda row: (row['有效链接数'] / row['链接数'] * 100) if row['链接数'] > 0 else 0, axis=1)
        vendor_summary['收录率 (%)'] = vendor_summary.apply(lambda row: (row['收录链接数'] / row['链接数'] * 100) if row['链接数'] > 0 else 0, axis=1)
        vendor_summary['错误交付率 (%)'] = vendor_summary.apply(lambda row: (row['错误交付数'] / row['链接数'] * 100) if row['链接数'] > 0 else 0, axis=1)
        
        # 计算综合质量分 (新权重，只关注正面指标)
        weights = {'有效链接率 (%)': 0.3, '收录率 (%)': 0.7}
        vendor_summary['综合质量分'] = (
            vendor_summary['有效链接率 (%)'] * weights['有效链接率 (%)'] +
            vendor_summary['收录率 (%)'] * weights['收录率 (%)']
        )
        
        # 计算成本和性价比
        vendor_summary['平均链接成本'] = vendor_summary.apply(lambda row: row['总花费'] / row['链接数'] if row['链接数'] > 0 else 0, axis=1)
        vendor_summary['性价比指数'] = vendor_summary.apply(lambda row: (row['综合质量分'] / row['平均链接成本']) * 10 if row['平均链接成本'] > 0 else 0, axis=1)
        
        display_vendor_df = vendor_summary.rename(columns={'vendor_name_text': '供应商'})

        st.dataframe(
            display_vendor_df.sort_values('性价比指数', ascending=False).style.format({
                '总花费': '${:,.2f}', '平均链接成本': '${:,.2f}',
                '有效链接率 (%)': '{:.1f}%', '收录率 (%)': '{:.1f}%', '错误交付率 (%)': '{:.1f}%',
                '综合质量分': '{:.1f}', '性价比指数': '{:.1f}'
            }).background_gradient(cmap='Greens', subset=['性价比指数', '综合质量分']).background_gradient(cmap='Reds', subset=['错误交付率 (%)']),
            width='stretch',
            column_order=['供应商', '链接数', '总花费', '错误交付率 (%)', '有效链接率 (%)', '收录率 (%)', '综合质量分', '平均链接成本', '性价比指数']
        )
        with st.expander("ℹ️ 指标说明 (V3.6)"):
            st.markdown("""
            - **错误交付率 (%)**: 交付的链接中，存在硬伤（如 `Nofollow`, `404死链`, `侦测失败`）的链接占比。**此项指标越低越好**。
            - **有效链接率 (%)**: HTTP状态码为 2xx (成功) 或 3xx (跳转) 的链接占总链接的百分比。
            - **收录率 (%)**: Google 已收录 (`page_indexed`) 的链接占总链接的百分比。
            - **综合质量分**: 根据交付链接的**上线成功率**和**收录成功率**加权计算的分数 (满分100)。**权重: 收录率(70%), 有效链接率(30%)。**
            - **平均链接成本**: 该供应商的总花费除以总链接数。
            - **性价比指数**: `(综合质量分 / 平均链接成本) * 10`。此分数越高，代表以相对更低的成本获得了更高质量的链接，性价比越高。
            """)

        st.markdown("---")
        st.header("数据明细")
        
        display_detail_df = filtered_df.copy()
        rename_map_display = {
            'purchase_date': '采购日期', 'website_name_text': '目标网站', 'vendor_name_text': '供应商',
            'domain_name_text': '外链域名', 'actual_cost': '花费',
            'google_index_status': '收录状态', 'detected_anchor_text': '侦测锚文本',
            'detected_link_type': '侦测链接类型', 'http_status': 'HTTP状态'
        }
        # 安全地获取列 ，避免KeyError
        display_detail_df = display_detail_df.get(list(rename_map_display.keys()), pd.DataFrame()).rename(columns=rename_map_display)
        
        def format_http_status_display(status ): return f"❌ {status}" if status == '404' else status
        def format_index_status_display(status): return f"✅ {status}" if status == 'page_indexed' else (f"❌ {status}" if status == 'page_not_indexed' else status)
        def format_anchor_text_display(text): return f"⚠️ {text}" if text in ["访问失败", "未找到链接", "最终失败", "Playwright超时"] else text

        if not display_detail_df.empty:
            display_detail_df['HTTP状态'] = display_detail_df['HTTP状态'].fillna('N/A').apply(format_http_status_display )
            display_detail_df['收录状态'] = display_detail_df['收录状态'].fillna('N/A').apply(format_index_status_display)
            display_detail_df['侦测锚文本'] = display_detail_df['侦测锚文本'].fillna('N/A').apply(format_anchor_text_display)
            st.dataframe(display_detail_df.sort_values('采购日期', ascending=False), width='stretch')
