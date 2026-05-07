# pages/Data_Center.py

import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io
from datetime import datetime
import re

# --- 配置与 Supabase 客户端 ---
st.set_page_config(layout="wide", page_title="SEO 数据中心")
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 初始化 Session State ---
if 'user_choices' not in st.session_state: st.session_state.user_choices = {}
if 'confirm_clear_offers' not in st.session_state: st.session_state.confirm_clear_offers = None
if 'domains_to_move' not in st.session_state: st.session_state.domains_to_move = None
if 'confirm_move_low_quality' not in st.session_state: st.session_state.confirm_move_low_quality = False
if 'orphaned_domains_result' not in st.session_state: st.session_state.orphaned_domains_result = None
if 'browser_df' not in st.session_state: st.session_state.browser_df = None
# ✨ 新增 Session State 用于“复活”功能
if 'domains_to_revive' not in st.session_state: st.session_state.domains_to_revive = None


# --- 辅助函数和消息显示 ---
def clean_domain(domain):
    if not isinstance(domain, str): return ""
    domain = domain.lower().strip()
    if domain.startswith("https://" ): domain = domain[8:]
    elif domain.startswith("http://" ): domain = domain[7:]
    if domain.startswith("www."): domain = domain[4:]
    slash_pos = domain.find('/')
    if slash_pos != -1: domain = domain[:slash_pos]
    if domain.endswith('/'): domain = domain[:-1]
    return domain

def format_days_to_years_days(days):
    if days is None or pd.isna(days): return "N/A"
    try:
        days = int(days); years = days // 365; remaining_days = days % 365
        return f"{years}年, {remaining_days}天" if years > 0 else f"{remaining_days}天"
    except (ValueError, TypeError): return "N/A"

def parse_age_string(age_str):
    if not isinstance(age_str, str) or not age_str.strip(): return None
    total_days = 0
    age_str = age_str.lower().strip()
    if not re.search(r'\d', age_str): return None
    if age_str.isdigit(): return int(age_str)
    year_match = re.search(r'(\d+)\s*(?:year|y)', age_str)
    if year_match: total_days += int(year_match.group(1)) * 365
    month_match = re.search(r'(\d+)\s*(?:month|m)', age_str)
    if month_match: total_days += int(month_match.group(1)) * 30
    day_match = re.search(r'(\d+)\s*(?:day|d)', age_str)
    if day_match: total_days += int(day_match.group(1))
    return total_days if total_days > 0 else None

if "user_message" in st.session_state and st.session_state.user_message:
    msg_type, msg_text = st.session_state.user_message
    if msg_type == "success": st.toast(f"✅ {msg_text}")
    elif msg_type == "error": st.error(msg_text)
    st.session_state.user_message = None

if 'messages' not in st.session_state: st.session_state.messages = []
for msg_type, msg_text in st.session_state.messages:
    if msg_type == "success": st.success(msg_text)
    elif msg_type == "warning": st.warning(msg_text)
    elif msg_type == "info": st.info(msg_text)
st.session_state.messages = []

for key in ['conflict_groups', 'non_conflicting_df', 'user_choices']:
    if key not in st.session_state: st.session_state[key] = None

# --- 页面标题和Tabs ---
st.title("📊 SEO 数据中心")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📝 **供应商报价管理**", "🌐 **域名指标中心**", "🏢 **网站管理**",
    "📉 **低质量域名**", "🚫 **域名黑名单管理**", "⭐ **优质域名管理**"
])

# --- Tab 1: 供应商报价管理 (无改动) ---
with tab1:
    st.subheader("📇 供应商档案管理")
    @st.cache_data(ttl=300)
    def get_all_vendors_details():
        response = supabase.table('vendors').select('*').order('name').execute()
        return response.data if response.data else []
    all_vendors = get_all_vendors_details()
    vendor_names = [v['name'] for v in all_vendors]
    st.write("##### 快速查找供应商")
    selected_vendor_name = st.selectbox("选择一个供应商查看信息:", options=[""] + vendor_names, label_visibility="collapsed", help="在这里快速查找供应商的详细档案。")
    if selected_vendor_name:
        vendor_details = next((v for v in all_vendors if v['name'] == selected_vendor_name), None)
        if vendor_details:
            with st.expander("✏️ 编辑此供应商信息", expanded=False):
                with st.form(key=f"edit_vendor_{vendor_details['id']}", clear_on_submit=False):
                    st.write(f"**正在编辑: {vendor_details['name']}**")
                    platform_options, article_options, status_options, vendor_type_options = ["teams", "website", "email"], ["vendor", "own"], ["active", "stop"], ["vendor", "direct owner", "platform"]
                    try: platform_index = platform_options.index(vendor_details.get('order_platform', 'teams'))
                    except ValueError: platform_index = 0
                    try: article_index = article_options.index(vendor_details.get('article_provider', 'vendor'))
                    except ValueError: article_index = 0
                    try: status_index = status_options.index(vendor_details.get('status', 'active'))
                    except ValueError: status_index = 0
                    try: vendor_type_index = vendor_type_options.index(vendor_details.get('vendor_type', 'vendor'))
                    except ValueError: vendor_type_index = 0
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        order_platform = st.selectbox("下单平台", options=platform_options, index=platform_index)
                        payment_method = st.text_input("支付方式", value=vendor_details.get('payment_method') or "")
                    with c2:
                        order_details = st.text_input("平台衍生信息", value=vendor_details.get('order_details') or "", help="团队成员名、网址或邮箱")
                        article_provider = st.selectbox("文章来源", options=article_options, index=article_index)
                    with c3: status = st.selectbox("合作状态", options=status_options, index=status_index, help="Active: 正常合作 | Stop: 暂停合作")
                    with c4: vendor_type = st.selectbox("供应商类型", options=vendor_type_options, index=vendor_type_index)
                    if st.form_submit_button("💾 保存更新"):
                        update_data = {'order_platform': order_platform, 'order_details': order_details, 'payment_method': payment_method, 'article_provider': article_provider, 'status': status, 'vendor_type': vendor_type}
                        try:
                            supabase.table('vendors').update(update_data).eq('id', vendor_details['id']).execute()
                            st.session_state.user_message = ("success", f"成功更新了供应商 '{vendor_details['name']}' 的信息！")
                            st.cache_data.clear(); st.rerun()
                        except Exception as e: st.error(f"更新失败: {e}")
            status_val, status_color = vendor_details.get('status', 'active'), "green" if vendor_details.get('status', 'active') == 'active' else "red"
            st.markdown(f"#### 供应商: {vendor_details['name']} <span style='color:{status_color};'>●</span> `{status_val}`", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3); c4, c5, _ = st.columns(3)
            with c1: st.markdown(f"- **下单平台**: `{vendor_details.get('order_platform', 'N/A')}`")
            with c2: st.markdown(f"- **支付方式**: `{vendor_details.get('payment_method', 'N/A')}`")
            with c3: st.markdown(f"- **供应商类型**: `{vendor_details.get('vendor_type', 'vendor')}`")
            with c4: st.markdown(f"- **平台衍生信息**: `{vendor_details.get('order_details', 'N/A')}`")
            with c5: st.markdown(f"- **文章来源**: `{vendor_details.get('article_provider', 'N/A')}`")
            st.markdown("---")
            with st.container(border=True):
                st.markdown("##### ⚠️ 危险操作")
                if st.session_state.confirm_clear_offers != vendor_details['id']:
                    if st.button(f"🗑️ 清空 {vendor_details['name']} 的所有Offer", type="primary"):
                        st.session_state.confirm_clear_offers = vendor_details['id']; st.rerun()
                else:
                    st.warning(f"**您确定要永久删除供应商 '{vendor_details['name']}' 的所有报价单吗？此操作不可撤销！**")
                    btn_col1, btn_col2, _ = st.columns([1, 1, 4])
                    with btn_col1:
                        if st.button("✅ 是，确认清空", type="primary"):
                            with st.spinner(f"正在删除 {vendor_details['name']} 的所有报价..."):
                                supabase.table('vendor_offers').delete().eq('vendor_id', vendor_details['id']).execute()
                            st.session_state.confirm_clear_offers = None; st.session_state.user_message = ("success", f"成功清空了 {vendor_details['name']} 的所有报价！")
                            st.cache_data.clear(); st.rerun()
                    with btn_col2:
                        if st.button("❌ 否，我点错了"): st.session_state.confirm_clear_offers = None; st.rerun()
    with st.expander("➕ 新增一个供应商"):
        with st.form(key="new_vendor_form", clear_on_submit=True):
            st.write("**正在新增供应商**")
            new_vendor_name = st.text_input("供应商名称 (必填)")
            c1, c2, c3 = st.columns(3)
            with c1:
                order_platform = st.selectbox("下单平台 ", options=["teams", "website", "email"], index=0)
                payment_method = st.text_input("支付方式 (e.g., PAYPAL) ")
            with c2:
                order_details = st.text_input("平台衍生信息 ", help="根据左侧平台填写：团队成员名、网址或邮箱")
                article_provider = st.selectbox("文章来源 ", options=["vendor", "own"], index=0)
            with c3: vendor_type = st.selectbox("供应商类型 ", options=["vendor", "direct owner", "platform"], index=0)
            if st.form_submit_button("➕ 创建新供应商"):
                if not new_vendor_name: st.warning("供应商名称是必填项！")
                else:
                    insert_data = {'name': new_vendor_name, 'order_platform': order_platform, 'order_details': order_details, 'payment_method': payment_method, 'article_provider': article_provider, 'status': 'active', 'vendor_type': vendor_type}
                    try:
                        supabase.table('vendors').insert(insert_data).execute()
                        st.session_state.user_message = ("success", f"成功创建了新供应商 '{new_vendor_name}'！")
                        st.cache_data.clear(); st.rerun()
                    except Exception as e:
                        if 'duplicate key value violates unique constraint' in str(e): st.error(f"创建失败：供应商名称 '{new_vendor_name}' 已存在！")
                        else: st.error(f"创建失败: {e}")
    st.markdown("---")
    with st.expander("📂 上传新的 Vendor 报价单", expanded=True):
        if st.session_state.conflict_groups:
            st.subheader("🚨 冲突解决中心")
            st.warning(f"文件中发现 {len(st.session_state.conflict_groups)} 组需要您决策的冲突。请为每一组选择要保留的记录。")
            for i, (group_key, group_df) in enumerate(st.session_state.conflict_groups.items()):
                st.markdown(f"---"); st.markdown(f"**冲突组: {group_key[0]} (Vendor: {group_key[1]})**")
                radio_key = f"choice_{i}"; options = [(f"保留此条: 价格 ${row['price']} (原文件第 {index + 2} 行)", index) for index, row in group_df.iterrows()]
                choice = st.radio("请选择一个版本保留：", options, format_func=lambda x: x[0], key=radio_key, index=len(options) - 1)
                st.session_state.user_choices[group_key] = choice[1]
            col1, col2 = st.columns(2)
            if col1.button("✅ 确认选择并继续处理", type="primary"):
                resolved_rows = [st.session_state.conflict_groups[group_key].loc[[selected_index]] for group_key, selected_index in st.session_state.user_choices.items()]
                final_df = pd.concat([st.session_state.non_conflicting_df] + resolved_rows) if resolved_rows else st.session_state.non_conflicting_df
                with st.spinner(f"正在处理 {len(final_df)} 条最终确认的报价..."):
                    final_df.drop_duplicates(subset=['domain_name', 'vendor'], keep='last', inplace=True)
                    vendors_in_file = list(final_df['vendor'].unique())
                    existing_vendors_res = supabase.rpc('get_vendor_ids_by_names', {'names': vendors_in_file}).execute()
                    vendor_map = {v['name']: v['id'] for v in existing_vendors_res.data}
                    new_vendors_to_create = [{'name': v} for v in vendors_in_file if v not in vendor_map]
                    if new_vendors_to_create:
                        new_vendors_res = supabase.table('vendors').insert(new_vendors_to_create).execute()
                        for v in new_vendors_res.data: vendor_map[v['name']] = v['id']
                    all_domains_in_file = list(final_df['domain_name'].unique())
                    existing_domains_res = supabase.rpc('get_domain_ids_by_names', {'names': all_domains_in_file}).execute()
                    domain_map = {d['domain_name']: d['id'] for d in existing_domains_res.data}
                    new_domains_to_create = [{'domain_name': d} for d in all_domains_in_file if d not in domain_map]
                    if new_domains_to_create:
                        new_domains_res = supabase.table('referring_domains').insert(new_domains_to_create).execute()
                        for d in new_domains_res.data: domain_map[d['domain_name']] = d['id']
                    offers_to_insert = [{'vendor_id': vendor_map.get(row['vendor']), 'rd_id': domain_map.get(row['domain_name']), 'price': row['price']} for _, row in final_df.iterrows() if domain_map.get(row['domain_name']) and vendor_map.get(row['vendor'])]
                    if offers_to_insert: supabase.table('vendor_offers').upsert(offers_to_insert, on_conflict='vendor_id, rd_id').execute()
                st.session_state.messages.append(("success", f"冲突已解决！成功录入/更新了 {len(offers_to_insert)} 条报价。"))
                st.session_state.conflict_groups, st.session_state.non_conflicting_df, st.session_state.user_choices = None, None, {}
                st.balloons(); st.cache_data.clear(); st.rerun()
            if col2.button("❌ 取消并重新上传"): st.session_state.conflict_groups, st.session_state.non_conflicting_df, st.session_state.user_choices = None, None, {}; st.rerun()
        else:
            st.info("上传包含 `domain_name`, `vendor`, `price` 列的 Excel/CSV 文件。")
            uploaded_offer_file = st.file_uploader("上传混合报价单文件", type=['xlsx', 'csv'], key="offer_uploader")
            if uploaded_offer_file:
                try:
                    df = pd.read_csv(uploaded_offer_file) if uploaded_offer_file.name.endswith('.csv') else pd.read_excel(uploaded_offer_file)
                    df.columns = [col.lower().strip() for col in df.columns]
                    if not {'domain_name', 'vendor', 'price'}.issubset(df.columns): st.error(f"文件缺少必要的列: domain_name, vendor, price")
                    else:
                        st.write("文件预览:"); st.dataframe(df.head())
                        if st.button("🚀 检查并处理文件", type="primary"):
                            df['domain_name'] = df['domain_name'].apply(clean_domain)
                            df.drop_duplicates(inplace=True)
                            conflicting_mask = df.duplicated(subset=['domain_name', 'vendor'], keep=False)
                            conflicting_df, non_conflicting_df = df[conflicting_mask], df[~conflicting_mask]
                            if conflicting_df.empty:
                                with st.spinner(f"未发现冲突，正在处理 {len(non_conflicting_df)} 条报价..."):
                                    final_df_no_conflict = non_conflicting_df.copy()
                                    vendors_in_file = list(final_df_no_conflict['vendor'].unique())
                                    existing_vendors_res = supabase.rpc('get_vendor_ids_by_names', {'names': vendors_in_file}).execute()
                                    vendor_map = {v['name']: v['id'] for v in existing_vendors_res.data}
                                    new_vendors_to_create = [{'name': v} for v in vendors_in_file if v not in vendor_map]
                                    if new_vendors_to_create:
                                        new_vendors_res = supabase.table('vendors').insert(new_vendors_to_create).execute()
                                        for v in new_vendors_res.data: vendor_map[v['name']] = v['id']
                                    all_domains_in_file = list(final_df_no_conflict['domain_name'].unique())
                                    existing_domains_res = supabase.rpc('get_domain_ids_by_names', {'names': all_domains_in_file}).execute()
                                    domain_map = {d['domain_name']: d['id'] for d in existing_domains_res.data}
                                    new_domains_to_create = [{'domain_name': d} for d in all_domains_in_file if d not in domain_map]
                                    if new_domains_to_create:
                                        new_domains_res = supabase.table('referring_domains').insert(new_domains_to_create).execute()
                                        for d in new_domains_res.data: domain_map[d['domain_name']] = d['id']
                                    offers_to_insert = [{'vendor_id': vendor_map.get(row['vendor']), 'rd_id': domain_map.get(row['domain_name']), 'price': row['price']} for _, row in final_df_no_conflict.iterrows() if domain_map.get(row['domain_name']) and vendor_map.get(row['vendor'])]
                                    if offers_to_insert: supabase.table('vendor_offers').upsert(offers_to_insert, on_conflict='vendor_id, rd_id').execute()
                                st.session_state.messages.append(("success", f"处理完毕！成功录入/更新了 {len(non_conflicting_df)} 条报价。"))
                                st.balloons(); st.cache_data.clear(); st.rerun()
                            else:
                                st.session_state.non_conflicting_df = non_conflicting_df
                                st.session_state.conflict_groups = {group_key: group_df for group_key, group_df in conflicting_df.groupby(['domain_name', 'vendor'])}
                                st.rerun()
                except Exception as e: st.error(f"处理文件时出错: {e}")
    st.markdown("---")
    with st.expander("📥 报价数据导出中心"):
        st.info("在这里，您可以根据供应商筛选并下载其所有的原始报价数据。")
        all_vendor_names = [v['name'] for v in all_vendors]
        selected_vendors_for_download = st.multiselect("选择要下载其报价的供应商 (可多选，不选则为全部):", options=all_vendor_names, key="download_vendor_select")
        @st.cache_data(ttl=60)
        def get_offers_for_download(vendor_names_list=None):
            query = supabase.table('vendor_offers').select("vendors!inner(name), referring_domains(domain_name), price")
            if vendor_names_list: query = query.in_('vendors.name', vendor_names_list)
            response = query.execute()
            if not response.data: return pd.DataFrame()
            df = pd.json_normalize(response.data, sep='_').rename(columns={'vendors_name': 'vendor', 'referring_domains_domain_name': 'domain_name'})
            if 'vendor' not in df.columns: st.error(f"数据处理失败：无法找到供应商列。当前可用列为: {df.columns.tolist()}"); return pd.DataFrame()
            return df[['vendor', 'domain_name', 'price']]
        vendors_to_query = selected_vendors_for_download if selected_vendors_for_download else all_vendor_names
        df_to_download = get_offers_for_download(vendors_to_query)
        if df_to_download.empty: st.warning("根据您的选择，没有找到任何报价数据可供下载。")
        else:
            st.write(f"准备下载 **{len(df_to_download)}** 条报价记录。预览如下:"); st.dataframe(df_to_download.head(), width='stretch')
            @st.cache_data
            def convert_df_to_csv(df): return df.to_csv(index=False).encode('utf-8')
            csv_data = convert_df_to_csv(df_to_download)
            st.download_button(label=f"📥 下载这 {len(df_to_download)} 条报价 (CSV)", data=csv_data, file_name=f"vendor_offers_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv', width='stretch', type="primary")

# --- Tab 2: 域名指标中心 ---
with tab2:
    st.header("🔎 域名指标与分类编辑器")
    st.info("从下拉列表中选择一个域名，查看并编辑其核心指标、分类和报价。")
    if 'editor_selected_domain' not in st.session_state: st.session_state.editor_selected_domain = ""
    if 'editor_domain_data' not in st.session_state: st.session_state.editor_domain_data = None

    @st.cache_data(ttl=600)
    def get_all_domain_names():
        response = supabase.table('referring_domains').select('domain_name').order('domain_name').execute()
        return [""] + [item['domain_name'] for item in response.data] if response.data else [""]
    all_domain_names = get_all_domain_names()

    selected_domain = st.selectbox("输入或选择一个域名进行编辑:", options=all_domain_names, index=all_domain_names.index(st.session_state.editor_selected_domain) if st.session_state.editor_selected_domain in all_domain_names else 0, key="domain_editor_selectbox")

    if selected_domain != st.session_state.editor_selected_domain:
        st.session_state.editor_selected_domain = selected_domain
        if selected_domain:
            with st.spinner(f"正在查找 '{selected_domain}' 的数据..."):
                domain_response = supabase.table('referring_domains').select('*').eq('domain_name', selected_domain).single().execute()
                if domain_response.data:
                    domain_data = domain_response.data
                    offers_response = supabase.table('vendor_offers').select('id, price, vendors(name)').eq('rd_id', domain_data['id']).eq('status', 'active').execute()
                    domain_data['vendor_offers'] = offers_response.data if offers_response.data else []
                    st.session_state.editor_domain_data = domain_data
                else: st.session_state.editor_domain_data = {}
        else: st.session_state.editor_domain_data = None
        st.rerun()

    if st.session_state.editor_domain_data:
        domain_data = st.session_state.editor_domain_data
        st.subheader(f"指标详情: `{domain_data.get('domain_name')}`")
        metric1, metric2, metric3, metric4, metric5 = st.columns(5)
        metric1.metric("DA", f"{domain_data.get('da', 'N/A')}")
        metric2.metric("DR", f"{domain_data.get('dr', 'N/A')}")
        traffic_value = domain_data.get('organic_traffic')
        metric3.metric("流量", f"{int(traffic_value):,}" if pd.notna(traffic_value) else "N/A")
        age_days = domain_data.get('age_in_days')
        if pd.notna(domain_data.get('first_seen_date')):
            try: age_days = (pd.Timestamp.now(tz='UTC') - pd.to_datetime(domain_data['first_seen_date']).tz_localize('UTC')).days
            except: pass
        metric4.metric("年龄", format_days_to_years_days(age_days))
        metric5.metric("类别", f"{domain_data.get('category', 'N/A')}")

        # ✨ 新增分类编辑功能
        st.markdown("---")
        st.subheader("分类管理")
        category_options = ['general', 'news', 'casino', 'ugc', 'platform', 'n/a']
        current_category = domain_data.get('category', 'n/a')
        try: cat_index = category_options.index(current_category)
        except ValueError: cat_index = category_options.index('n/a')

        new_category = st.selectbox("域名分类:", options=category_options, index=cat_index, key=f"cat_select_{domain_data['id']}")
        if new_category != current_category:
            if st.button("💾 更新分类", key=f"cat_update_{domain_data['id']}"):
                try:
                    supabase.table('referring_domains').update({'category': new_category}).eq('id', domain_data['id']).execute()
                    st.session_state.user_message = ("success", f"域名 '{domain_data['domain_name']}' 的分类已更新为 '{new_category}'！")
                    st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"分类更新失败: {e}")

        st.markdown("---")
        st.subheader(f"编辑报价列表")
        offers = domain_data.get('vendor_offers', [])
        if not offers: st.warning("该域名当前没有可编辑的报价。")
        else:
            records = [{'offer_id': offer.get('id'), 'vendor_name': offer.get('vendors', {}).get('name', 'N/A'), 'price': offer.get('price')} for offer in offers]
            original_df = pd.DataFrame(records)
            original_df.insert(0, "删除", False)
            edited_df = st.data_editor(original_df, key="domain_quick_editor", width='stretch', hide_index=True, column_config={"offer_id": None, "vendor_name": "供应商", "price": st.column_config.NumberColumn("价格 ($)", format="$%.2f"), "删除": st.column_config.CheckboxColumn("删除报价?")}, disabled=['vendor_name'])
            save_col, _ = st.columns([1, 3])
            with save_col:
                if st.button("💾 应用所有更改", type="primary", width='stretch'):
                    archived_count, updated_count = 0, 0
                    to_archive_df = edited_df[edited_df['删除'] == True]
                    if not to_archive_df.empty:
                        archive_ids = to_archive_df['offer_id'].tolist()
                        with st.spinner(f"正在归档 {len(archive_ids)} 条报价..."):
                            try:
                                update_response = supabase.table('vendor_offers').update({'status': 'archived'}).in_('id', archive_ids).execute()
                                if update_response.data: archived_count = len(update_response.data)
                            except Exception as e: st.error(f"归档报价时出错: {e}")
                    remaining_df = edited_df[edited_df['删除'] == False]
                    comparison_df = pd.merge(original_df[['offer_id', 'price']], remaining_df[['offer_id', 'price']], on='offer_id', suffixes=('_orig', '_new'))
                    diff_df = comparison_df[comparison_df['price_orig'] != comparison_df['price_new']]
                    if not diff_df.empty:
                        updates_to_make = []
                        for _, row in diff_df.iterrows():
                            price_value = row['price_new'] if pd.notna(row['price_new']) else None
                            updates_to_make.append({'id': int(row['offer_id']), 'price': price_value})
                        
                        if updates_to_make:
                            with st.spinner(f"正在更新 {len(updates_to_make)} 条价格..."):
                                try:
                                    update_price_response = supabase.table('vendor_offers').upsert(updates_to_make).execute()
                                    if update_price_response.data: updated_count = len(update_price_response.data)
                                except Exception as e: st.error(f"更新价格时出错: {e}")
                    
                    if archived_count > 0 or updated_count > 0:
                        st.success(f"操作成功！归档了 {archived_count} 条报价，更新了 {updated_count} 条价格。")
                        st.session_state.editor_selected_domain = ""
                        st.session_state.editor_domain_data = None
                        st.cache_data.clear(); st.rerun()
                    else: st.info("没有检测到任何更改。")

    st.markdown("---")
    with st.expander("🚀 批量更新指标与分类"):
        st.info("上传包含 `domain_name` 和其他指标（da, dr, organic_traffic, age, **category**）的文件，以批量更新数据库。")
        uploaded_metrics_file = st.file_uploader("上传指标文件", type=['xlsx', 'csv'], key="metrics_uploader")
        if uploaded_metrics_file:
            try:
                df_metrics = pd.read_csv(uploaded_metrics_file) if uploaded_metrics_file.name.endswith('.csv') else pd.read_excel(uploaded_metrics_file)
                df_metrics.columns = [col.lower().strip() for col in df_metrics.columns]
                if 'domain_name' not in df_metrics.columns: st.error("指标文件必须包含 'domain_name' 列。")
                else:
                    df_metrics['domain_name'] = df_metrics['domain_name'].apply(clean_domain)
                    st.write("指标文件预览 (已清理域名):"); st.dataframe(df_metrics.head())
                    if st.button("开始批量更新指标", type="primary"):
                        st.subheader("🔍 诊断日志"); log_container = st.container(height=300); update_count = 0
                        with st.spinner(f"正在逐条更新 {len(df_metrics)} 个域名的指标..."):
                            for index, row in df_metrics.iterrows():
                                domain_to_update = row['domain_name']; update_data = {}
                                if 'da' in row and pd.notna(row['da']): update_data['da'] = row['da']
                                if 'dr' in row and pd.notna(row['dr']): update_data['dr'] = row['dr']
                                if 'organic_traffic' in row and pd.notna(row['organic_traffic']): update_data['organic_traffic'] = row['organic_traffic']
                                # ✨ 新增: 支持批量更新 category
                                if 'category' in row and pd.notna(row['category']): update_data['category'] = row['category']
                                if 'first_seen_date' in row and pd.notna(row['first_seen_date']):
                                    try: update_data['first_seen_date'] = pd.to_datetime(row['first_seen_date']).isoformat()
                                    except Exception: log_container.warning(f"⚠️ 域名 `{domain_to_update}` 的 first_seen_date 格式无效，已跳过。")
                                if 'age' in row and pd.notna(row['age']):
                                    age_days = parse_age_string(str(row['age']))
                                    if age_days is not None: update_data['age_in_days'] = age_days
                                
                                if update_data:
                                    update_data['last_updated_at'] = datetime.now().isoformat()
                                    try:
                                        log_container.write(f"正在为域名: `{domain_to_update}` 寻找匹配并更新...")
                                        response = supabase.table('referring_domains').update(update_data).eq('domain_name', domain_to_update).execute()
                                        if response.data: log_container.success(f"✅ 成功找到并更新了 `{domain_to_update}`。"); update_count += 1
                                        else: log_container.warning(f"⚠️ 未能在数据库中找到 `{domain_to_update}` 的匹配项。跳过。")
                                    except Exception as e: log_container.error(f"更新 `{domain_to_update}` 时出错: {e}")
                                else: log_container.info(f"ℹ️ 域名 `{domain_to_update}` 在文件中没有需要更新的指标。跳过。")
                        st.session_state.user_message = ("success", f"指标更新完毕！共成功更新了 {update_count} 个域名。")
                        st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"处理指标文件时出错: {e}")

    with st.expander("📥 下载待办列表"):
        st.info("下载的文件将包含所有指标列的表头，方便您直接填写并重新上传。")
        
        # ✨ 1. 新增第三个下载选项
        download_option = st.radio(
            "选择要下载的域名列表：", 
            (
                '仅下载缺少指标的域名', 
                '下载所有有价值的域名',
                '下载数据库所有域名 (无过滤)' # <--- 新增选项
            ),
            index=1, # 默认选中“下载所有有价值的域名”
            key="download_radio"
        )
        
        # ✨ 2. 彻底移除旧的 exclude_low_quality 开关
        # col1, col2 = st.columns(2) ... (这部分UI被简化了)

        # ✨ 3. 改造 get_domains_for_scan 函数以支持新选项
        @st.cache_data(ttl=300)
        def get_domains_for_scan(option):
            try:
                if option == '下载数据库所有域名 (无过滤)':
                    # --- 逻辑A: 获取所有未归档的域名，无任何其他过滤 ---
                    query = supabase.table('referring_domains').select(
                        'domain_name, da, dr, organic_traffic, category, language'
                    ).eq('is_archived', False)
                    response = query.execute()

                else: # 适用于“缺少指标”和“有价值”的选项
                    # --- 逻辑B: 调用包含所有过滤规则的数据库函数 ---
                    query = supabase.rpc('get_available_domains').select(
                        'domain_name, da, dr, organic_traffic, category, language'
                    )
                    response = query.execute()

                if not response.data:
                    return pd.DataFrame()
                
                df = pd.DataFrame(response.data)

                # 如果用户只想下载缺少指标的，就在这里进行最终筛选
                if option == '仅下载缺少指标的域名':
                    df = df[
                        df['da'].isnull() | 
                        df['dr'].isnull() | 
                        df['organic_traffic'].isnull() |
                        df['category'].isnull() |
                        df['language'].isnull()
                    ]

                return df

            except Exception as e:
                st.error(f"获取待办列表时发生严重错误！")
                st.code(f"{e}")
                return pd.DataFrame()

        # --- ✨ 4. 简化UI渲染逻辑 ---
        
        result_df = get_domains_for_scan(option=download_option)
        
        # 动态生成按钮标签
        if download_option == '仅下载缺少指标的域名':
            button_label_suffix = "缺少指标的域名"
        elif download_option == '下载所有有价值的域名':
            button_label_suffix = "全部有价值的域名"
        else: # 下载所有
            button_label_suffix = "数据库所有域名"
        
        if not result_df.empty:
            domains_to_download = result_df['domain_name'].tolist()
            button_label = f"下载 {len(domains_to_download)} 个 {button_label_suffix}"
            
            headers = ['domain_name', 'da', 'dr', 'organic_traffic', 'first_seen_date', 'age', 'category', 'language']
            df_download = pd.DataFrame(columns=headers)
            df_download['domain_name'] = domains_to_download
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_download.to_excel(writer, index=False, sheet_name='metrics_to_update')
            
            st.download_button(
                label=button_label, 
                data=output.getvalue(), 
                file_name='metrics_to_update.xlsx', 
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                width='stretch'
            )
        else:
            # 根据不同选项显示不同的提示信息
            if download_option == '仅下载缺少指标的域名':
                st.success("✅ 太棒了！目前没有需要补充指标的域名。")
            else:
                st.warning("⚠️ 根据您的选择，没有找到任何可供下载的域名。")

    # --- 以下功能保持不变 ---
    with st.expander("🧹 孤儿指标清理"):
        st.info("此功能会查找并分类那些不再有活跃报价的域名，您可以选择将它们归档以保持数据库整洁。")
        @st.cache_data(ttl=300)
        def get_all_orphaned_domains():
            try:
                response = supabase.rpc('get_orphaned_referring_domains').execute()
                return response.data if response.data else []
            except Exception as e:
                if "function get_orphaned_referring_domains() does not exist" in str(e): return {"error": "db_function_not_found"}
                st.error(f"查找孤儿域名时出错: {e}"); return []
        if st.session_state.orphaned_domains_result is None:
            if st.button("🔍 查找所有可清理的域名"):
                with st.spinner("正在数据库中查找并分类孤儿域名..."): st.session_state.orphaned_domains_result = get_all_orphaned_domains()
                st.rerun()
        else:
            orphaned_data = st.session_state.orphaned_domains_result
            if isinstance(orphaned_data, dict) and orphaned_data.get("error") == "db_function_not_found": st.error("错误：数据库函数 `get_orphaned_referring_domains` 不存在。请在 Supabase SQL Editor 中运行最新的函数代码。")
            elif not orphaned_data:
                st.success("✅ 非常棒！您的数据库目前没有发现任何可清理的孤儿域名。")
                if st.button("重新检查"): st.session_state.orphaned_domains_result = None; st.cache_data.clear(); st.rerun()
            else:
                df_orphans = pd.DataFrame(orphaned_data)
                true_orphans_df = df_orphans[df_orphans['orphan_type'] == 'True Orphan'].copy()
                disconnected_df = df_orphans[df_orphans['orphan_type'] == 'Disconnected'].copy()
                st.warning(f"检查完毕！共发现 {len(df_orphans)} 个可清理的域名。")
                tab_true, tab_disconnected = st.tabs([f"🪦 彻底的孤儿 ({len(true_orphans_df)})", f"🔌 失联的域名 ({len(disconnected_df)})"])
                with tab_true:
                    st.markdown("**定义**: 这些域名在系统中没有任何报价记录，是明确的“僵尸数据”，建议直接归档。")
                    if true_orphans_df.empty: st.info("没有找到彻底的孤儿域名。")
                    else:
                        true_orphans_df.insert(0, "选择归档", True)
                        edited_true_orphans = st.data_editor(true_orphans_df.drop(columns=['orphan_type']), column_config={"选择归档": st.column_config.CheckboxColumn(default=True), "id": "ID", "domain_name": "域名", "da": "DA", "dr": "DR", "organic_traffic": "流量", "last_updated_at": st.column_config.DatetimeColumn("最后更新于", format="YYYY-MM-DD HH:mm")}, disabled=true_orphans_df.columns.drop("选择归档"), hide_index=True, width='stretch', key="true_orphans_editor")
                        selected_to_archive_true = edited_true_orphans[edited_true_orphans["选择归档"]]
                        if not selected_to_archive_true.empty:
                            if st.button(f"🗑️ 归档所选的 {len(selected_to_archive_true)} 个彻底孤儿", type="primary", key="archive_true_orphans"):
                                ids_to_archive = selected_to_archive_true['id'].tolist(); errors = []
                                with st.spinner(f"正在归档 {len(ids_to_archive)} 个域名..."):
                                    for domain_id in ids_to_archive:
                                        try: supabase.rpc('archive_domain', {'domain_id_to_archive': domain_id}).execute()
                                        except Exception as e: errors.append(f"归档域名ID {domain_id} 时失败: {str(e)}")
                                if errors: st.error("处理过程中出现错误："); st.json(errors)
                                else: st.session_state.messages.append(("success", f"成功归档了 {len(ids_to_archive)} 个彻底孤儿域名。")); st.session_state.orphaned_domains_result = None; st.cache_data.clear(); st.rerun()
                with tab_disconnected:
                    st.markdown("**定义**: 这些域名过去曾有过报价，但现在所有报价都已失效（被归档）。")
                    if disconnected_df.empty: st.info("没有找到失联的域名。")
                    else:
                        disconnected_df.insert(0, "选择归档", True)
                        edited_disconnected = st.data_editor(disconnected_df.drop(columns=['orphan_type']), column_config={"选择归档": st.column_config.CheckboxColumn(default=True), "id": "ID", "domain_name": "域名", "da": "DA", "dr": "DR", "organic_traffic": "流量", "last_updated_at": st.column_config.DatetimeColumn("最后更新于", format="YYYY-MM-DD HH:mm")}, disabled=disconnected_df.columns.drop("选择归档"), hide_index=True, width='stretch', key="disconnected_editor")
                        selected_to_archive_disconnected = edited_disconnected[edited_disconnected["选择归档"]]
                        if not selected_to_archive_disconnected.empty:
                            if st.button(f"🗑️ 归档所选的 {len(selected_to_archive_disconnected)} 个失联域名", type="secondary", key="archive_disconnected"):
                                ids_to_archive = selected_to_archive_disconnected['id'].tolist(); errors = []
                                with st.spinner(f"正在归档 {len(ids_to_archive)} 个域名..."):
                                    for domain_id in ids_to_archive:
                                        try: supabase.rpc('archive_domain', {'domain_id_to_archive': domain_id}).execute()
                                        except Exception as e: errors.append(f"归档域名ID {domain_id} 时失败: {str(e)}")
                                if errors: st.error("处理过程中出现错误："); st.json(errors)
                                else: st.session_state.messages.append(("success", f"成功归档了 {len(ids_to_archive)} 个失联域名。")); st.session_state.orphaned_domains_result = None; st.cache_data.clear(); st.rerun()
                if st.button("重新检查所有可清理域名"): st.session_state.orphaned_domains_result = None; st.cache_data.clear(); st.rerun()

    with st.expander("📉 识别并隔离低质量域名"):
        st.info("**此功能帮助您根据设定的标准找出低质量域名，并将它们从主数据库移动到“低质量域名”列表中进行隔离管理。**")
        st.subheader("第1步: 定义低质量域名的标准")
        logic_operator = st.radio("匹配逻辑", options=["or", "and"], index=0, horizontal=True, help="选择 '或' 表示满足任意一个条件即为低质量；选择 '与' 表示必须满足所有条件。")
        clean_col1, clean_col2, clean_col3 = st.columns(3)
        max_da = clean_col1.number_input("DA 低于 (<=)", min_value=0, max_value=100, value=20)
        max_dr = clean_col2.number_input("DR 低于 (<=)", min_value=0, max_value=100, value=20)
        max_traffic = clean_col3.number_input("Traffic 低于 (<=)", min_value=0, value=0)
        if st.button("🔍 查找符合条件的低质量域名", width='stretch'):
            with st.spinner("正在根据您的标准查找低质量域名..."):
                try:
                    query = supabase.table('referring_domains').select('id, domain_name, da, dr, organic_traffic')
                    if logic_operator == "and": query = query.lte('da', max_da).lte('dr', max_dr).lte('organic_traffic', max_traffic)
                    else: query = query.or_(f"da.lte.{max_da},dr.lte.{max_dr},organic_traffic.lte.{max_traffic}")
                    response = query.execute()
                    st.session_state.domains_to_move = pd.DataFrame(response.data) if response.data else pd.DataFrame()
                except Exception as e: st.error(f"查找域名时出错: {e}"); st.session_state.domains_to_move = None
            st.rerun()
        if st.session_state.domains_to_move is not None:
            df_to_move = st.session_state.domains_to_move
            if df_to_move.empty:
                st.success("✅ 非常棒！根据您的标准，没有找到需要隔离的低质量域名。")
                if st.button("好的"): st.session_state.domains_to_move = None; st.rerun()
            else:
                st.subheader("第2步: 预览将要被隔离的数据")
                st.warning(f"根据您的标准，共找到 **{len(df_to_move)}** 个低质量域名。这些域名及其所有关联的报价将被**从主数据库中移除**，并添加到“低质量域名”列表中。")
                st.dataframe(df_to_move, width='stretch')
                st.subheader("第3步: 最终确认与执行")
                if not st.session_state.confirm_move_low_quality:
                    if st.button("🚚 执行隔离操作", type="primary", width='stretch'): st.session_state.confirm_move_low_quality = True; st.rerun()
                else:
                    st.error("**最终警告：此操作将从主数据库移除数据，请确认！**")
                    final_confirm_col1, final_confirm_col2 = st.columns(2)
                    with final_confirm_col1:
                        if st.button("✅ 是的，我确认隔离", width='stretch'):
                            domain_ids_to_process = df_to_move['id'].tolist()
                            domain_names_to_add_to_list = df_to_move['domain_name'].tolist()
                            errors = []
                            with st.spinner(f"正在隔离 {len(domain_ids_to_process)} 个域名..."):
                                try:
                                    records_to_insert = [{"domain_name": name} for name in domain_names_to_add_to_list]
                                    supabase.table('low_quality_domains').upsert(records_to_insert, on_conflict='domain_name').execute()
                                except Exception as e: errors.append(f"添加到低质量列表失败: {e}")
                                if not errors:
                                    for domain_id in domain_ids_to_process:
                                        try: supabase.rpc('archive_domain', {'domain_id_to_archive': domain_id}).execute()
                                        except Exception as e: errors.append(f"归档域名ID {domain_id} 时失败: {e}")
                            if errors: st.error("处理过程中出现一个或多个错误："); [st.warning(err) for err in errors]
                            else: st.session_state.user_message = ("success", f"操作完成！成功隔离并归档了 {len(domain_ids_to_process)} 个域名。")
                            st.session_state.domains_to_move = None; st.session_state.confirm_move_low_quality = False; st.cache_data.clear(); st.rerun()
                    with final_confirm_col2:
                        if st.button("❌ 否，取消操作", width='stretch'): st.session_state.domains_to_move = None; st.session_state.confirm_move_low_quality = False; st.rerun()

# --- 通用的列表管理UI函数 (无改动) ---
def render_list_management_ui(list_name, table_name, help_text, icon):
    st.header(f"{icon} {list_name}管理")
    st.info(help_text)
    @st.cache_resource(ttl=3600)
    def check_table_exists(t_name):
        try: supabase.table(t_name).select('id', head=True).execute(); return True
        except Exception: return False
    if not check_table_exists(table_name):
        st.error(f"错误：数据库中缺少名为 `{table_name}` 的表。请联系管理员创建。"); return
    @st.cache_data(ttl=300)
    def get_list_domains(target_table):
        response = supabase.table(target_table).select('id, domain_name, created_at').order('domain_name').execute()
        return response.data if response.data else []
    current_domains = get_list_domains(table_name)
    current_domain_set = {d['domain_name'] for d in current_domains}
    with st.form(key=f"add_single_form_{table_name}", clear_on_submit=True):
        st.subheader("单个添加"); new_domain = st.text_input("域名", key=f"single_domain_input_{table_name}")
        if st.form_submit_button(f"➕ 添加到{list_name}") and new_domain:
            cleaned_domain = clean_domain(new_domain)
            if cleaned_domain:
                if cleaned_domain in current_domain_set: st.warning(f"域名 '{cleaned_domain}' 已在列表中。")
                else:
                    try: supabase.table(table_name).insert({"domain_name": cleaned_domain}).execute(); st.session_state.user_message = ("success", f"成功将 '{cleaned_domain}' 添加到{list_name}！"); st.cache_data.clear(); st.rerun()
                    except Exception as e: st.error(f"添加失败: {e}")
            else: st.warning("请输入一个有效的域名。")
    with st.expander(f"📂 批量上传到{list_name}"):
        uploaded_file = st.file_uploader("上传只包含一列 `domain_name` 的文件", type=['xlsx', 'csv'], key=f"uploader_{table_name}")
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                df.columns = [col.lower().strip() for col in df.columns]
                if 'domain_name' not in df.columns: st.error("文件必须包含 'domain_name' 列。")
                else:
                    df['cleaned_domain'] = df['domain_name'].apply(clean_domain)
                    new_domains_to_add = list(set(df['cleaned_domain'].dropna()) - current_domain_set)
                    if not new_domains_to_add: st.info(f"文件中的所有域名都已存在于{list_name}中。")
                    else:
                        st.write(f"文件中共找到 {len(new_domains_to_add)} 个新域名将被添加:"); st.dataframe(pd.DataFrame(new_domains_to_add, columns=["新域名"]), width='stretch', height=200)
                        if st.button(f"确认批量添加到{list_name}", type="primary", key=f"batch_add_button_{table_name}"):
                            with st.spinner(f"正在添加 {len(new_domains_to_add)} 个域名..."):
                                records = [{"domain_name": d} for d in new_domains_to_add]
                                supabase.table(table_name).insert(records).execute()
                                st.session_state.user_message = ("success", f"成功批量添加了 {len(new_domains_to_add)} 个域名！"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"处理文件时出错: {e}")
    st.markdown("---")
    st.subheader(f"📜 当前{list_name}列表 ({len(current_domains)} 个)")
    if not current_domains: st.info(f"您的{list_name}中还没有任何域名。")
    else:
        df_display = pd.DataFrame(current_domains); df_display.insert(0, "选择移除", False)
        edited_df = st.data_editor(df_display, column_config={"选择移除": st.column_config.CheckboxColumn(default=False), "id": None, "domain_name": "域名", "created_at": st.column_config.DatetimeColumn("添加时间", format="YYYY-MM-DD HH:mm")}, disabled=df_display.columns.drop("选择移除"), hide_index=True, width='stretch', key=f"editor_{table_name}")
        selected_to_delete = edited_df[edited_df["选择移除"]]
        if not selected_to_delete.empty:
            if st.button(f"🗑️ 从{list_name}中移除所选的 {len(selected_to_delete)} 个域名", type="primary", key=f"delete_button_{table_name}"):
                with st.expander("⚠️ **请确认操作**", expanded=True):
                    st.warning(f"您确定要从{list_name}中移除这 {len(selected_to_delete)} 个域名吗？")
                    if st.button("是的，确认移除", key=f"confirm_delete_{table_name}"):
                        ids_to_delete = selected_to_delete['id'].tolist()
                        with st.spinner("正在执行移除操作..."): supabase.table(table_name).delete().in_('id', ids_to_delete).execute()
                        st.session_state.user_message = ("success", f"成功移除了 {len(ids_to_delete)} 个域名。"); st.cache_data.clear(); st.rerun()

# --- Tab 3: 网站管理 (最终版 v9 - 增加Status管理) ---
with tab3:
    st.header("🏢 网站管理")
    st.info("管理网站以及关联的URL。")

    @st.cache_data(ttl=300)
    def get_website_management_data():
        projects_res = supabase.table('projects').select('id, project_name').execute()
        # ✨ 1. 从 client_websites 表中多获取 status 字段
        websites_res = supabase.table('client_websites').select('id, name, project_id, status').execute()
        urls_res = supabase.table('website_urls').select('id, client_website_id, url, url_type').execute()
        return pd.DataFrame(projects_res.data), pd.DataFrame(websites_res.data), pd.DataFrame(urls_res.data)

    projects_df, websites_df, urls_df = get_website_management_data()
    project_map = projects_df.set_index('id')['project_name'].to_dict()

    with st.expander("➕ 新增一个网站"):
        with st.form(key="new_website_form", clear_on_submit=True):
            st.write("**填写新网站信息**"); new_website_name = st.text_input("网站名称", key="new_site_name")
            selected_project_name = st.selectbox("选择所属项目", options=projects_df['project_name'].tolist(), key="new_site_project")
            if st.form_submit_button("➕ 创建新网站") and new_website_name and selected_project_name:
                project_id = projects_df[projects_df['project_name'] == selected_project_name]['id'].iloc[0]
                try:
                    # ✨ 2. 新增网站时，默认将 status 设置为 'active'
                    insert_data = {
                        'name': new_website_name, 
                        'project_id': int(project_id),
                        'status': 'active' 
                    }
                    supabase.table('client_websites').insert(insert_data).execute()
                    st.session_state.user_message = ("success", f"成功创建了新网站 '{new_website_name}'！")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e: st.error(f"创建网站失败: {e}")

    st.markdown("---"); st.subheader("📜 网站列表")
    if websites_df.empty:
        st.info("您还没有添加任何网站。")
    else:
        website_names = ["-- 请选择 --"] + websites_df['name'].tolist()
        selected_website = st.selectbox("选择一个网站进行管理:", options=website_names, key="manage_website_select")

        if selected_website != "-- 请选择 --":
            details = websites_df[websites_df['name'] == selected_website].iloc[0]
            website_id = details['id']

            with st.container(border=True):
                st.markdown(f"##### 编辑网站: **{details['name']}**")
                with st.form(key=f"edit_website_{website_id}"):
                    # ✨ 3. 将布局从2列改为3列，为 status 留出空间
                    c1, c2, c3 = st.columns(3)
                    
                    with c1:
                        new_name = st.text_input("网站名称", value=details['name'])
                    
                    with c2:
                        proj_opts = projects_df['project_name'].tolist()
                        try: proj_idx = proj_opts.index(project_map.get(details.get('project_id'), ''))
                        except ValueError: proj_idx = 0
                        new_proj_name = st.selectbox("Project", options=proj_opts, index=proj_idx)

                    # ✨ 4. 新增 status 编辑框
                    with c3:
                        status_options = ['active', 'inactive']
                        # 获取当前 status，如果不存在则默认为 'active'
                        current_status = details.get('status', 'active')
                        try:
                            status_idx = status_options.index(current_status)
                        except ValueError:
                            status_idx = 0 # 如果数据库里的值不是 active/inactive，也默认为 active
                        new_status = st.selectbox("状态", options=status_options, index=status_idx)

                    if st.form_submit_button("💾 保存网站信息"):
                        new_proj_id = projects_df[projects_df['project_name'] == new_proj_name]['id'].iloc[0]
                        try:
                            # ✨ 5. 在 update 数据中加入 status
                            update_data = {
                                'name': new_name, 
                                'project_id': int(new_proj_id),
                                'status': new_status
                            }
                            supabase.table('client_websites').update(update_data).eq('id', website_id).execute()
                            st.session_state.user_message = ("success", "网站信息更新成功！")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e: st.error(f"更新失败: {e}")

            # --- 编辑/删除 和 批量新增 URL 的部分保持不变，无需修改 ---
            
            # --- 1. 编辑和删除现有的URL ---
            st.markdown("---"); st.markdown(f"##### ✏️ 编辑/删除 关联的URL")
            original_urls_df = urls_df[urls_df['client_website_id'] == website_id].copy()
            
            if original_urls_df.empty:
                st.info("该网站还没有关联的URL。请在下方新增。")
            else:
                display_df = original_urls_df.copy()
                display_df.insert(0, "删除", False)

                edited_urls_df = st.data_editor(
                    display_df,
                    num_rows="fixed", 
                    column_config={
                        "id": None, "client_website_id": None,
                        "url": st.column_config.TextColumn("URL", required=True),
                        "url_type": st.column_config.TextColumn("URL 类型", required=True),
                        "删除": st.column_config.CheckboxColumn("删除?")
                    },
                    hide_index=True, width='stretch', key=f"urls_editor_{website_id}"
                )

                if st.button("💾 保存对以上列表的修改", key=f"save_edits_{website_id}"):
                    try:
                        ids_to_delete = edited_urls_df[edited_urls_df['删除'] == True]['id'].dropna().tolist()
                        if ids_to_delete:
                            supabase.table('website_urls').delete().in_('id', [str(i) for i in ids_to_delete]).execute()

                        records_to_update = []
                        active_edited_df = edited_urls_df[edited_urls_df['删除'] == False]
                        for _, row in active_edited_df.iterrows():
                            original_row = original_urls_df[original_urls_df['id'] == row['id']].iloc[0]
                            if original_row['url'] != row['url'] or original_row['url_type'] != row['url_type']:
                                records_to_update.append({
                                    'id': str(row['id']),
                                    'url': str(row['url']).strip(),
                                    'url_type': str(row['url_type']).strip()
                                })
                        
                        if records_to_update:
                            supabase.table('website_urls').upsert(records_to_update).execute()
                        
                        st.success("编辑/删除操作成功！")
                        st.cache_data.clear()
                        st.rerun()

                    except Exception as e:
                        st.error("在编辑/删除时发生错误！")
                        st.exception(e)

            # --- 2. 使用独立的表单进行批量新增 ---
            st.markdown("---"); st.markdown(f"##### ➕ 批量新增URL")
            with st.form(key=f"batch_add_urls_form_{website_id}", clear_on_submit=True):
                st.info("每行粘贴一条 URL。您可以指定 URL 类型，用逗号、Tab或空格隔开。如果未指定，类型默认为 'general'。")
                
                placeholder_text = (
                    "https://example.com/page1, a-type\n"
                    "https://example.com/page2 b-type\n"
                    "https://example.com/page3\t\tc-type\n"
                    "https://example.com/page4"
                 )
                
                urls_to_add_text = st.text_area("粘贴要新增的URL (每行一条):", height=200, placeholder=placeholder_text)
                
                if st.form_submit_button("🚀 确认批量新增"):
                    if urls_to_add_text and urls_to_add_text.strip():
                        lines = urls_to_add_text.strip().split('\n')
                        records_to_insert = []
                        
                        for line in lines:
                            if not line or not line.strip():
                                continue
                            
                            parts = re.split(r'[,\s\t]+', line.strip(), maxsplit=1)
                            url = parts[0]
                            url_type = parts[1].strip() if len(parts) > 1 and parts[1].strip() else 'general'
                            
                            records_to_insert.append({
                                'client_website_id': str(website_id),
                                'url': url,
                                'url_type': url_type
                            })

                        if records_to_insert:
                            try:
                                response = supabase.table('website_urls').insert(records_to_insert).execute()
                                st.success(f"成功批量新增了 {len(response.data)} 条URL！")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error("批量新增URL时发生错误！")
                                st.exception(e)
                        else:
                            st.warning("没有找到有效的URL进行添加。")
                    else:
                        st.warning("输入框不能为空！")

# --- Tab 4: 低质量域名管理 ---
with tab4:
    render_list_management_ui(list_name="低质量域名", table_name="low_quality_domains", help_text="这里存放了通过“识别并隔离低质量域名”功能找出的域名。您可以查看、移除或手动添加域名。", icon="📉")

    st.markdown("---") # 分隔线

    # ✨ [核心改动] 新增“检查与恢复”功能模块
    with st.expander("♻️ 检查并恢复有价值的域名"):
        st.info(
            "此功能会检查当前列表中的域名，如果它们的最新指标已达标，"
            "您可以将它们从该列表中移除，使其恢复到主推荐池中。"
        )

        st.subheader("第1步: 定义“恢复”标准")
        col1, col2, col3 = st.columns(3)
        min_da = col1.number_input("DA 恢复到 (>=)", min_value=0, value=20, key="revive_da")
        min_dr = col2.number_input("DR 恢复到 (>=)", min_value=0, value=20, key="revive_dr")
        min_traffic = col3.number_input("Traffic 恢复到 (>=)", min_value=0, value=100, key="revive_traffic")
        
        if st.button("🔍 查找所有可恢复的域名", width='stretch', key="find_revivable"):
            with st.spinner("正在交叉比对低质量列表与最新域名指标..."):
                try:
                    # 1. 获取所有低质量域名的名字
                    lq_res = supabase.table('low_quality_domains').select('domain_name').execute()
                    if not lq_res.data:
                        st.success("低质量列表中没有任何域名可供检查。")
                        st.session_state.domains_to_revive = pd.DataFrame()
                    else:
                        lq_names = [d['domain_name'] for d in lq_res.data]
                        
                        # 2. 在主表中查找这些域名的最新指标，并应用恢复标准
                        # 注意：这里我们不能用 archive_domain 函数，因为那些域名还在主表里，只是被标记了
                        # 我们的逻辑是把它们移到 low_quality_domains，但原数据还在 referring_domains
                        metrics_res = supabase.table('referring_domains') \
                            .select('domain_name, da, dr, organic_traffic') \
                            .in_('domain_name', lq_names) \
                            .gte('da', min_da) \
                            .gte('dr', min_dr) \
                            .gte('organic_traffic', min_traffic) \
                            .execute()
                        
                        if metrics_res.data:
                            st.session_state.domains_to_revive = pd.DataFrame(metrics_res.data)
                        else:
                            st.session_state.domains_to_revive = pd.DataFrame()
                except Exception as e:
                    st.error(f"查找可恢复域名时出错: {e}")
                    st.session_state.domains_to_revive = None
            st.rerun()

        if st.session_state.domains_to_revive is not None:
            df_to_revive = st.session_state.domains_to_revive
            if df_to_revive.empty:
                st.success("✅ 根据您的标准，没有找到可以恢复的域名。")
            else:
                st.subheader("第2步: 预览并确认恢复")
                st.warning(f"找到 **{len(df_to_revive)}** 个已达标的域名，可以将它们从低质量列表中移除。")
                st.dataframe(df_to_revive, width='stretch')

                if st.button(f"✅ 确认恢复这 {len(df_to_revive)} 个域名", type="primary", key="confirm_revive"):
                    names_to_remove = df_to_revive['domain_name'].tolist()
                    with st.spinner("正在从低质量列表中移除已恢复的域名..."):
                        try:
                            supabase.table('low_quality_domains').delete().in_('domain_name', names_to_remove).execute()
                            st.session_state.user_message = ("success", f"成功恢复了 {len(names_to_remove)} 个域名！")
                            st.session_state.domains_to_revive = None
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"恢复域名时出错: {e}")
            
            if st.button("重新检查", key="revive_recheck"):
                st.session_state.domains_to_revive = None
                st.rerun()


# --- Tab 5: 黑名单管理 ---
with tab5:
    render_list_management_ui(
        list_name="域名黑名单",
        table_name="domain_blacklist",
        help_text="在这里管理您不希望出现在任何推荐结果中的域名。被分类为 'ugc' 或 'platform' 的域名会自动被过滤，无需手动加入黑名单。",
        icon="🚫"
    )

# --- Tab 6: 优质名单管理 ---
with tab6:
    render_list_management_ui(
        list_name="优质域名",
        table_name="domain_premiumlist",
        help_text="在这里管理您认为的优质域名，它们将在推荐结果中被高亮标记。",
        icon="⭐"
    )

# --- 完整代码结束 ---
