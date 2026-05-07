# pages/6_Purchase_Analytics.py

import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date, timezone, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import re
import time
import numpy as np
import cloudscraper
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 配置 ---
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

INDEXCHECKR_API_KEY = st.secrets.get("indexcheckr_api_key")
INDEXCHECKR_PROJECT_ID = st.secrets.get("indexcheckr_project_id_2")

st.set_page_config(layout="wide")
st.title("📥 采购历史管理")

tab1, tab2 = st.tabs(["⬆️ 上传采购记录", "📊 采购分析与链接监控"])

# ==============================================================================
# --- 标签页 1 (无变化) ---
# ==============================================================================
with tab1:
    # ... (此部分代码与V15.0完全相同，为简洁起见省略)
    st.header("批量上传采购记录")
    st.info(
        """
        **新模式：直接记录，后期关联**
        1.  您只需上传包含基本信息的表格，所有记录都会被直接存入采购历史。
        2.  系统会**尝试**在后台关联到具体的“报价”，如果失败，记录依然会保存。
        3.  您可以在“采购分析与修正”标签页中，对未关联的记录进行后期修正和关联。
        """
    )
    st.markdown("#### 1. 下载并填写模板")
    template_data = {
        'domain_name': ['example.com', 'sample.org'], 'live_link': ['https://example.com/post', 'https://sample.org/post'],
        'vendor_name': ['SEO-Vendor-A', 'SEO-Vendor-B'], 'website_name': ['wsscc.org', 'wsscc.org'],
        'actual_cost': [150, 200], 'purchase_date': ['03-07-2025', '04-07-2025']
    }
    template_df = pd.DataFrame(template_data )
    @st.cache_data
    def convert_df_to_csv(df): return df.to_csv(index=False).encode('utf-8')
    csv = convert_df_to_csv(template_df)
    st.download_button("下载 Excel 模板 (.csv)", csv, 'purchase_history_template.csv', 'text/csv')
    st.markdown("---")
    st.markdown("#### 2. 上传填写好的文件")
    uploaded_file = st.file_uploader("选择一个 CSV 或 XLSX 文件", type=['csv', 'xlsx'], key="purchase_uploader_v15_2")
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.write("预览上传的数据："); st.dataframe(df.head())
            if st.button("开始处理并写入数据库", type="primary"):
                required_columns = {'domain_name', 'vendor_name', 'website_name', 'actual_cost', 'purchase_date'}
                if not required_columns.issubset(df.columns):
                    st.error(f"文件缺少必要的列: {required_columns - set(df.columns)}"); st.stop()
                with st.spinner("正在处理和上传记录..."):
                    unique_domains = df['domain_name'].unique().tolist(); unique_vendors = df['vendor_name'].unique().tolist(); unique_websites = df['website_name'].unique().tolist()
                    offers_query = supabase.table('vendor_offers').select('id, referring_domains!inner(domain_name), vendors!inner(name)').in_('referring_domains.domain_name', unique_domains).in_('vendors.name', unique_vendors).execute()
                    websites_query = supabase.table('client_websites').select('id, name').in_('name', unique_websites).execute()
                    offer_map = {(offer['referring_domains']['domain_name'], offer['vendors']['name']): offer['id'] for offer in offers_query.data}
                    website_map = {site['name']: site['id'] for site in websites_query.data}
                    records_to_insert = []
                    for index, row in df.iterrows():
                        domain, vendor, website = row['domain_name'], row['vendor_name'], row['website_name']
                        offer_id = offer_map.get((domain, vendor)); website_id = website_map.get(website)
                        try:
                            purchase_datetime = pd.to_datetime(row['purchase_date'], dayfirst=True)
                        except (ValueError, TypeError):
                            st.error(f"行 {index+2} 的日期格式无法识别: {row['purchase_date']}。请使用 DD-MM-YYYY 或 YYYY-MM-DD 格式。"); st.stop()
                        record = {'purchase_date': purchase_datetime.isoformat(), 'actual_cost': row['actual_cost'], 'live_link': row.get('live_link') if pd.notna(row.get('live_link')) else None, 'domain_name_text': domain, 'vendor_name_text': vendor, 'website_name_text': website, 'website_id': website_id, 'offer_id': offer_id}
                        records_to_insert.append(record)
                try:
                    supabase.table('purchase_history').insert(records_to_insert).execute()
                    st.success(f"✅ 成功上传并记录了 **{len(records_to_insert)}** 条采购历史！"); st.info("您现在可以前往“采购分析与修正”标签页查看和管理这些记录。"); st.balloons(); st.cache_data.clear()
                except Exception as e:
                    st.error(f"数据库写入失败: {e}")
        except Exception as e: st.error(f"处理文件时发生意外错误：{e}")


# ==============================================================================
# --- 标签页 2 (✨ V15.2 核心修正) ---
# ==============================================================================
with tab2:
    st.header("采购分析与链接监控")

    # --- 函数定义部分 ---
    @st.cache_resource
    def get_requests_session_with_retry():
        session = requests.Session()
        retry_strategy = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter )
        session.mount("https://", adapter )
        return session

    def format_check_date(date_str):
        if not date_str or pd.isna(date_str):
            return "N/A"
        try:
            dt_object = pd.to_datetime(date_str)
            if dt_object.tzinfo is None:
                dt_object = dt_object.tz_localize('UTC')
            gmt8_tz = timezone(timedelta(hours=8))
            gmt8_dt = dt_object.astimezone(gmt8_tz)
            return gmt8_dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return "日期无效"

    def format_http_status(status ):
        if status == '404': return f"❌ {status}"
        return status

    def format_index_status(status):
        if status == 'page_not_indexed': return f"❌ {status}"
        if status == 'page_indexed': return f"✅ {status}"
        return status

    def format_anchor_text(text):
        if text in ["访问失败", "未找到链接", "最终失败", "Playwright超时"]: return f"⚠️ {text}"
        return text

    @st.cache_data(ttl=30)
    def load_all_purchase_data():
        query = "id, purchase_date, actual_cost, live_link, domain_name_text, vendor_name_text, website_name_text, website_id, offer_id, google_index_status, indexcheckr_page_id, google_index_last_check, detected_anchor_text, detected_link_type, http_status, backlink_last_check, backlink_lost_date"
        response = supabase.table('purchase_history' ).select(query).order('purchase_date', desc=True).execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()

    # --- 爬虫和API函数 (无变化) ---
    def check_http_status(live_link ):
        session = get_requests_session_with_retry()
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'}
            response = session.head(live_link, headers=headers, timeout=45, allow_redirects=True)
            return str(response.status_code)
        except requests.exceptions.Timeout: return "超时"
        except requests.exceptions.ConnectionError: return "链接错误"
        except requests.exceptions.RequestException: return "请求失败"

    def parse_html_for_links(html_content, target_url):
        found_results = []
        soup = BeautifulSoup(html_content, 'lxml')
        target_pattern = re.sub(r'https?://(www\. )?', '', target_url).strip('/')
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if not href: continue
            href_pattern = re.sub(r'https?://(www\. )?', '', href).strip('/')
            if target_pattern in href_pattern:
                actual_anchor = a_tag.get_text(strip=True)
                rel_attr = a_tag.get('rel', [])
                is_nofollow = 'nofollow' in rel_attr
                found_results.append({"anchor": actual_anchor, "type": "Nofollow" if is_nofollow else "Dofollow"})
        return found_results

    def find_backlinks_with_playwright(live_link, target_url):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(live_link, timeout=60000, wait_until='domcontentloaded')
                html_content = page.content()
                browser.close()
                return parse_html_for_links(html_content, target_url)
        except PlaywrightTimeoutError: return "Playwright超时"
        except Exception: return "Playwright失败"

    def find_backlinks(live_link, target_url):
        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(live_link, timeout=45)
            response.raise_for_status()
            return parse_html_for_links(response.content, target_url)
        except (requests.exceptions.Timeout, cloudscraper.exceptions.CloudflareChallengeError):
            return find_backlinks_with_playwright(live_link, target_url)
        except Exception:
            try:
                session = get_requests_session_with_retry()
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'}
                response = session.get(live_link, headers=headers, timeout=45, allow_redirects=True)
                response.raise_for_status()
                return parse_html_for_links(response.content, target_url)
            except requests.exceptions.Timeout: return find_backlinks_with_playwright(live_link, target_url)
            except Exception: return "最终失败"

    def get_single_url_status_with_retry(live_link, headers):
        try:
            api_url_get = f"https://indexcheckr.com/api/v1/project/{INDEXCHECKR_PROJECT_ID}/pages"
            response = requests.get(api_url_get, headers=headers, params={'url': live_link}, timeout=30 )
            if response.ok:
                pages_status = response.json().get('data', [])
                if pages_status:
                    page_data = pages_status[0]
                    if page_data.get('status') == 'being_processed':
                        time.sleep(5)
                        response = requests.get(api_url_get, headers=headers, params={'url': live_link}, timeout=30)
                        if response.ok:
                            pages_status_retry = response.json().get('data', [])
                            if pages_status_retry: return pages_status_retry[0]
                    return page_data
        except requests.RequestException: return None
        return None

    # --- 主逻辑 ---
    all_df = load_all_purchase_data()

    if all_df.empty:
        st.info("采购历史为空，请先在“上传采购记录”标签页中上传数据。")
    else:
        # --- 数据预处理 ---
        all_df['purchase_date_obj'] = pd.to_datetime(all_df['purchase_date'], errors='coerce').dt.date

        valid_links = all_df.dropna(subset=['live_link'])
        all_df['is_duplicate'] = all_df['live_link'].isin(valid_links[valid_links.duplicated(subset=['live_link'], keep=False)]['live_link'])

        # 初始化新列
        for col in ['http_status', 'google_index_status', 'google_index_last_check', 'detected_anchor_text', 'detected_link_type', 'backlink_last_check', 'backlink_lost_date']:
            if col not in all_df.columns: all_df[col] = pd.NaT if 'date' in col or 'check' in col else 'N/A'
        
        # ✨ V15.2 核心修正 1: 直接创建最终显示的列 ，不再使用 '_display' 后缀
        all_df['采购日期'] = pd.to_datetime(all_df['purchase_date'], errors='coerce').dt.strftime('%Y-%m-%d')
        all_df['HTTP状态'] = all_df['http_status'].fillna('N/A' ).apply(format_http_status )
        all_df['收录状态'] = all_df['google_index_status'].fillna('N/A').apply(format_index_status)
        all_df['最后检查于'] = all_df['google_index_last_check'].apply(format_check_date)
        all_df['侦测锚文本'] = all_df['detected_anchor_text'].fillna('N/A').apply(format_anchor_text)
        all_df['侦测链接类型'] = all_df['detected_link_type'].fillna('N/A')
        all_df.loc[all_df['侦测锚文本'].str.contains('失败|未找到链接|超时', na=False), '侦测链接类型'] = 'N/A'
        all_df['Backlink最后检查于'] = all_df['backlink_last_check'].apply(format_check_date)
        all_df['Backlink丢失于'] = all_df['backlink_lost_date'].apply(format_check_date)

        # --- 筛选器 ---
        with st.expander("📊 数据筛选与视图控制", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                selected_websites = st.multiselect("按目标网站筛选", options=all_df['website_name_text'].dropna().unique())
                if not all_df['purchase_date_obj'].dropna().empty:
                    date_range = st.date_input("按采购日期筛选", value=(all_df['purchase_date_obj'].dropna().min(), all_df['purchase_date_obj'].dropna().max()))
                else:
                    date_range = st.date_input("按采购日期筛选", value=(date.today(), date.today()))
            with col2:
                selected_vendors = st.multiselect("按供应商筛选", options=all_df['vendor_name_text'].dropna().unique())
                selected_http_status = st.multiselect("按 HTTP 状态筛选", options=all_df['HTTP状态'].dropna( ).unique())
            with col3:
                selected_index_status = st.multiselect("按收录状态筛选", options=all_df['收录状态'].dropna().unique())
                detection_options = ['包含有效结果', '⚠️ 最终失败', '⚠️ 未找到链接', '⚠️ Playwright超时']
                selected_detection_status = st.multiselect("按侦测结果筛选", options=detection_options)
            
            # ✨ V15.6 核心修正: 使用比例数组强制实现紧凑的左右布局
            # 创建一个包含3列的布局，前两列较窄用于放置checkbox，第三列很宽用于占据剩余空间
            compact_cols = st.columns([1, 1, 4]) # 这个比例是关键: [窄, 窄, 宽]
            with compact_cols[0]:
                show_duplicates_only = st.checkbox("⚠️ 仅显示重复的 Live Link")
            with compact_cols[1]:
                show_lost_only = st.checkbox("💀 仅显示已丢失的链接")
            # 第三列 (compact_cols[2]) 我们什么都不放，它会自动成为一个看不见的空白占位符

        # --- 应用筛选 ---
        filtered_df = all_df.copy()
        if selected_websites: filtered_df = filtered_df[filtered_df['website_name_text'].isin(selected_websites)]
        if selected_vendors: filtered_df = filtered_df[filtered_df['vendor_name_text'].isin(selected_vendors)]
        if len(date_range) == 2 and not filtered_df['purchase_date_obj'].dropna().empty:
            filtered_df = filtered_df.dropna(subset=['purchase_date_obj'])
            filtered_df = filtered_df[filtered_df['purchase_date_obj'].between(date_range[0], date_range[1])]
        if selected_http_status: filtered_df = filtered_df[filtered_df['HTTP状态'].isin(selected_http_status )]
        if selected_index_status: filtered_df = filtered_df[filtered_df['收录状态'].isin(selected_index_status)]
        if selected_detection_status:
            conditions = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            if '包含有效结果' in selected_detection_status: conditions |= ~filtered_df['侦测锚文本'].isin(['⚠️ 最终失败', '⚠️ 未找到链接', '⚠️ Playwright超时', 'N/A'])
            if '⚠️ 最终失败' in selected_detection_status: conditions |= (filtered_df['侦测锚文本'] == '⚠️ 最终失败')
            if '⚠️ 未找到链接' in selected_detection_status: conditions |= (filtered_df['侦测锚文本'] == '⚠️ 未找到链接')
            if '⚠️ Playwright超时' in selected_detection_status: conditions |= (filtered_df['侦测锚文本'] == '⚠️ Playwright超时')
            filtered_df = filtered_df[conditions]
        
        if show_duplicates_only: filtered_df = filtered_df[filtered_df['is_duplicate'] == True]
        if show_lost_only: filtered_df = filtered_df[pd.notna(filtered_df['backlink_lost_date'])]

        # --- 表格展示 ---
        st.markdown("---")
        st.markdown("#### 可编辑的采购数据")
        
        select_all = st.checkbox("全选/取消全选所有可见链接", key="select_all_checkbox")
        
        filtered_df_for_display = filtered_df.copy()
        filtered_df_for_display.reset_index(drop=True, inplace=True)
        filtered_df_for_display.insert(0, '勾选操作', select_all)
        
        def get_status_display(row):
            if pd.notna(row['backlink_lost_date']): return "💀 已丢失"
            if row['is_duplicate']: return "⚠️ 重复"
            return "正常"
        
        filtered_df_for_display.insert(1, '状态', filtered_df_for_display.apply(get_status_display, axis=1))

        # ✨ V15.2 核心修正 2: 确保 display_columns 字典中的键在 DataFrame 中真实存在
        display_columns = {
            '状态': '状态', '采购日期': '采购日期', 'website_name_text': '目标网站', 'vendor_name_text': '供应商',
            'domain_name_text': '外链域名', 'actual_cost': '实际花费', 'live_link': 'Live链接',
            'HTTP状态': 'HTTP状态', '侦测锚文本': '侦测锚文本', '侦测链接类型': '侦测链接类型',
            '收录状态': '收录状态', '最后检查于': '最后检查于',
            'Backlink最后检查于': 'Backlink最后检查于', 'Backlink丢失于': 'Backlink丢失于'
        }

        editable_columns_map = {
            '目标网站': 'website_name_text', '供应商': 'vendor_name_text',
            '外链域名': 'domain_name_text', '实际花费': 'actual_cost', 'Live链接': 'live_link'
        }
        
        disabled_columns = [col for col in display_columns.values() if col not in editable_columns_map]

        # ✨ V15.2 核心修正 3: 确保只选择 DataFrame 中存在的列
        columns_to_display_in_editor = ['勾选操作', 'id'] + [col for col in display_columns.keys() if col in filtered_df_for_display.columns]
        
        edited_df = st.data_editor(
            filtered_df_for_display[columns_to_display_in_editor].rename(columns=display_columns),
            key="purchase_editor_v15_2",
            column_config={"Live链接": st.column_config.LinkColumn("Live链接", help="点击跳转到 Live Link 页面", display_text="🔗 打开链接")},
            disabled=disabled_columns, width='stretch', height=600, hide_index=True
        )
        st.markdown("---")
        st.subheader("⚙️ 批量自动化操作")
        
        rows_to_action = edited_df[edited_df['勾选操作']]
        
        col_check, col_refresh, col_validate, col_http_check = st.columns(4 )

        BATCH_SIZE = 10

        with col_check:
            if not rows_to_action.empty:
                if st.button(f"🔍 检查 {len(rows_to_action)} 项Google Index", type="secondary"):
                    if not INDEXCHECKR_API_KEY or not INDEXCHECKR_PROJECT_ID:
                        st.error("IndexCheckr API Key 或 Project ID 未配置。"); st.stop()
                    batches = np.array_split(rows_to_action, np.ceil(len(rows_to_action) / BATCH_SIZE))
                    total_batches = len(batches)
                    progress_bar = st.progress(0, text=f"准备开始处理 {total_batches} 个批次...")
                    for i, batch_df in enumerate(batches):
                        batch_num = i + 1
                        progress_bar.progress(i / total_batches, text=f"批次 {batch_num}/{total_batches}: 正在提交链接...")
                        for index, row in batch_df.iterrows():
                            live_link = row['Live链接']
                            if not live_link or not isinstance(live_link, str) or not live_link.startswith('http'  ): continue
                            payload = {"url": live_link, "checkPeriod": "none", "stopCheckWhenIndexed": True}
                            headers = {"Accept": "application/json", "Content-Type": "application/json", "X-AUTH-TOKEN": INDEXCHECKR_API_KEY}
                            try: requests.post(f"https://indexcheckr.com/api/v1/project/{INDEXCHECKR_PROJECT_ID}/pages", headers=headers, json=payload, timeout=30  )
                            except requests.RequestException: pass
                            time.sleep(0.5)
                        progress_bar.progress((i + 0.5) / total_batches, text=f"批次 {batch_num}/{total_batches}: 等待 API 处理...")
                        time.sleep(10)
                        updates_to_db = []
                        headers_get = {"Accept": "application/json", "X-AUTH-TOKEN": INDEXCHECKR_API_KEY}
                        for index, row in batch_df.iterrows():
                            live_link = row['Live链接']
                            if not live_link or not isinstance(live_link, str) or not live_link.startswith('http'  ): continue
                            page_data = get_single_url_status_with_retry(live_link, headers_get)
                            if page_data:
                                last_check_obj = page_data.get('lastCheckAt')
                                last_check_date = last_check_obj.get('date') if last_check_obj else None
                                original_id = int(row['id'])
                                updates_to_db.append({'id': original_id, 'indexcheckr_page_id': page_data.get('id'), 'google_index_status': page_data.get('status'), 'google_index_last_check': last_check_date})
                            time.sleep(0.5)
                        if updates_to_db:
                            try:
                                progress_bar.progress((i + 0.9) / total_batches, text=f"批次 {batch_num}/{total_batches}: 正在写入数据库...")
                                supabase.table('purchase_history').upsert(updates_to_db).execute()
                            except Exception as e: st.error(f"写入批次 {batch_num} 的数据时出错: {e}")
                    progress_bar.empty()
                    st.success(f"✅ 所有 {total_batches} 个批次处理完成！"); st.cache_data.clear(); st.rerun()

        with col_refresh:
            if not rows_to_action.empty:
                links_to_recheck = rows_to_action[rows_to_action['收录状态'] != 'N/A']
                if not links_to_recheck.empty:
                    if st.button(f"🔄 刷新 {len(links_to_recheck)} 项Google Index"):
                        batches = np.array_split(links_to_recheck, np.ceil(len(links_to_recheck) / BATCH_SIZE))
                        total_batches = len(batches)
                        progress_bar = st.progress(0, text=f"准备开始刷新 {total_batches} 个批次...")
                        for i, batch_df in enumerate(batches):
                            batch_num = i + 1
                            progress_bar.progress(i / total_batches, text=f"批次 {batch_num}/{total_batches}: 正在触发刷新...")
                            for index, row in batch_df.iterrows():
                                original_row_index = filtered_df_for_display.loc[index].name
                                page_id = filtered_df.loc[original_row_index, 'indexcheckr_page_id']
                                if pd.notna(page_id):
                                    api_url_recheck = f"https://indexcheckr.com/api/v1/project/{INDEXCHECKR_PROJECT_ID}/pages/{int(page_id )}/recheck"
                                    headers = {"Accept": "application/json", "X-AUTH-TOKEN": INDEXCHECKR_API_KEY}
                                    try: requests.put(api_url_recheck, headers=headers, timeout=30)
                                    except requests.RequestException: pass
                                    time.sleep(0.5)
                            progress_bar.progress((i + 0.5) / total_batches, text=f"批次 {batch_num}/{total_batches}: 等待 API 处理...")
                            time.sleep(10)
                            updates_to_db = []
                            headers_get = {"Accept": "application/json", "X-AUTH-TOKEN": INDEXCHECKR_API_KEY}
                            for index, row in batch_df.iterrows():
                                live_link = row['Live链接']
                                if not live_link or not isinstance(live_link, str) or not live_link.startswith('http' ): continue
                                page_data = get_single_url_status_with_retry(live_link, headers_get)
                                if page_data:
                                    last_check_obj = page_data.get('lastCheckAt')
                                    last_check_date = last_check_obj.get('date') if last_check_obj else None
                                    # ✨ V13.4 核心修正
                                    original_id = int(filtered_df_for_display.loc[index, 'id'])
                                    updates_to_db.append({'id': original_id, 'google_index_status': page_data.get('status'), 'google_index_last_check': last_check_date})
                                time.sleep(0.5)
                            if updates_to_db:
                                try:
                                    progress_bar.progress((i + 0.9) / total_batches, text=f"批次 {batch_num}/{total_batches}: 正在写入数据库...")
                                    supabase.table('purchase_history').upsert(updates_to_db).execute()
                                except Exception as e: st.error(f"写入刷新批次 {batch_num} 的数据时出错: {e}")
                        progress_bar.empty()
                        st.success(f"✅ 所有 {total_batches} 个刷新批次处理完成！"); st.cache_data.clear(); st.rerun()

        with col_validate:
            if not rows_to_action.empty:
                if st.button(f"🔗 验证/监控 {len(rows_to_action)} 项Backlink"):
                    batches = np.array_split(rows_to_action, np.ceil(len(rows_to_action) / BATCH_SIZE))
                    total_batches = len(batches)
                    progress_bar = st.progress(0, text=f"准备开始验证 {total_batches} 个批次...")
                    
                    current_time_utc = datetime.now(timezone.utc).isoformat()

                    for i, batch_df in enumerate(batches):
                        batch_num = i + 1
                        updates_to_db = []
                        for j, (index, row) in enumerate(batch_df.iterrows()):
                            progress_bar.progress((i + (j / len(batch_df))) / total_batches, text=f"批次 {batch_num}/{total_batches}: 验证 {row['Live链接'][:30]}...")
                            live_link = row['Live链接']
                            target_website = row['目标网站']
                            
                            if not all([live_link, target_website]): continue
                            
                            target_url = f"https://{target_website}" if not target_website.startswith('http' ) else target_website
                            results = find_backlinks(live_link, target_url)
                            
                            update_payload = {'id': int(row['id'])}
                            
                            is_found = isinstance(results, list) and results
                            # 安全地检查 backlink_lost_date 是否存在且有值
                            is_previously_lost = 'backlink_lost_date' in row and pd.notna(row['backlink_lost_date'])

                            if is_found:
                                anchor_text_summary = " | ".join([r['anchor'] for r in results])
                                link_type_summary = " | ".join([r['type'] for r in results])
                                update_payload.update({
                                    'detected_anchor_text': anchor_text_summary,
                                    'detected_link_type': link_type_summary,
                                    'backlink_last_check': current_time_utc
                                })
                                if is_previously_lost:
                                    update_payload['backlink_lost_date'] = None
                            else:
                                error_reason = "未找到链接" if isinstance(results, list) else results
                                update_payload.update({
                                    'detected_anchor_text': error_reason,
                                    'detected_link_type': 'N/A'
                                })
                                if not is_previously_lost:
                                    update_payload['backlink_lost_date'] = current_time_utc

                            updates_to_db.append(update_payload)
                            time.sleep(0.2)
                            
                        if updates_to_db:
                            try:
                                supabase.table('purchase_history').upsert(updates_to_db).execute()
                            except Exception as e:
                                st.error(f"写入批次 {batch_num} 的验证结果时出错: {e}")
                                
                    progress_bar.empty()
                    st.success(f"✅ 所有 {total_batches} 个验证批次处理完成！"); st.cache_data.clear(); st.rerun()

        with col_http_check:
            if not rows_to_action.empty:
                if st.button(f"🚦 检查 {len(rows_to_action )} 项HTTP状态"):
                    batches = np.array_split(rows_to_action, np.ceil(len(rows_to_action) / BATCH_SIZE))
                    total_batches = len(batches)
                    progress_bar = st.progress(0, text=f"准备开始检查 {total_batches} 个批次的链接状态...")
                    for i, batch_df in enumerate(batches):
                        batch_num = i + 1
                        updates_to_db = []
                        for j, (index, row) in enumerate(batch_df.iterrows()):
                            progress_bar.progress((i + (j / len(batch_df))) / total_batches, text=f"批次 {batch_num}/{total_batches}: 检查 {row['Live链接'][:30]}...")
                            live_link = row['Live链接']
                            if not live_link or not isinstance(live_link, str) or not live_link.startswith('http' ):
                                status = "链接无效"
                            else:
                                status = check_http_status(live_link )
                            # ✨ V13.4 核心修正
                            original_id = int(filtered_df_for_display.loc[index, 'id'])
                            updates_to_db.append({'id': original_id, 'http_status': status} )
                            time.sleep(0.1)
                        if updates_to_db:
                            try:
                                supabase.table('purchase_history').upsert(updates_to_db).execute()
                            except Exception as e:
                                st.error(f"写入批次 {batch_num} 的 HTTP 状态时出错: {e}")
                    progress_bar.empty()
                    st.success(f"✅ 所有 {total_batches} 个链接状态检查批次处理完成！"); st.cache_data.clear(); st.rerun()

        # --- 后期关联/修正工作流 ---
        st.markdown("---")
        st.subheader("✍️ 修正与关联操作")

        editable_columns_map = {
            '目标网站': 'website_name_text', '供应商': 'vendor_name_text',
            '外链域名': 'domain_name_text', '实际花费': 'actual_cost', 'Live链接': 'live_link'
        }

        original_df_subset = filtered_df_for_display.set_index('id')[list(editable_columns_map.values())]
        edited_df_subset = edited_df.set_index('id')[list(editable_columns_map.keys())]
        edited_df_subset.rename(columns=editable_columns_map, inplace=True)
        
        common_indices = original_df_subset.index.intersection(edited_df_subset.index)
        original_aligned = original_df_subset.loc[common_indices]
        edited_aligned = edited_df_subset.loc[common_indices]

        changed_rows_mask = (original_aligned.fillna('') != edited_aligned.fillna('')).any(axis=1)
        changed_indices = changed_rows_mask[changed_rows_mask].index
        
        changed_rows = edited_df[edited_df['id'].isin(changed_indices)]

        if not changed_rows.empty:
            st.warning("检测到以下数据已被修改。您可以勾选它们并执行操作。")
            
            changed_rows_with_selector = changed_rows.copy()
            changed_rows_with_selector.insert(0, '勾选以操作', False)
            
            selected_to_process = st.data_editor(
                changed_rows_with_selector, 
                key="process_changes_editor", 
                hide_index=True,
                disabled=changed_rows_with_selector.columns.drop('勾选以操作')
            )
            
            selected_rows = selected_to_process[selected_to_process['勾选以操作']]

            if not selected_rows.empty:
                col_save, col_link = st.columns(2)
                with col_save:
                    if st.button(f"💾 保存对 {len(selected_rows)} 项的文本修改", help="仅更新文本字段，不尝试关联。"):
                        updates = []
                        for index, row in selected_rows.iterrows():
                            updates.append({
                                'id': int(row['id']), 
                                'actual_cost': row['实际花费'], 
                                'live_link': row['Live链接'],
                                'website_name_text': row['目标网站'], 
                                'vendor_name_text': row['供应商'], 
                                'domain_name_text': row['外链域名']
                            })
                        supabase.table('purchase_history').upsert(updates).execute()
                        st.success("文本修改已保存！"); st.cache_data.clear(); st.rerun()

                with col_link:
                    if st.button(f"🔗 保存并尝试关联 {len(selected_rows)} 项", type="primary", help="更新文本并尝试查找匹配的 Offer ID 和 Website ID。"):
                        with st.spinner("正在保存并尝试关联..."):
                            updates = []
                            for index, row in selected_rows.iterrows():
                                offer_res = supabase.table('vendor_offers').select('id').eq('referring_domains.domain_name', row['外链域名']).eq('vendors.name', row['供应商']).single().execute()
                                website_res = supabase.table('client_websites').select('id').eq('name', row['目标网站']).single().execute()
                                updates.append({
                                    'id': int(row['id']), 
                                    'actual_cost': row['实际花费'], 
                                    'live_link': row['Live链接'],
                                    'website_name_text': row['目标网站'], 
                                    'vendor_name_text': row['供应商'], 
                                    'domain_name_text': row['外链域名'],
                                    'offer_id': offer_res.data['id'] if offer_res.data else None,
                                    'website_id': website_res.data['id'] if website_res.data else None
                                })
                            supabase.table('purchase_history').upsert(updates).execute()
                            st.success("操作完成！请检查记录状态。"); st.cache_data.clear(); st.rerun()