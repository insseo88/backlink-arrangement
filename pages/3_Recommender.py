# pages/3_Recommender.py

import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta
from sklearn.preprocessing import MinMaxScaler
import re
from streamlit_tags import st_tags

# --- Session State 初始化 ---
if 'selections' not in st.session_state:
    st.session_state.selections = {}
if 'sort_by' not in st.session_state:
    st.session_state.sort_by = 'recommend_score' # 默认排序字段

# --- 辅助函数等 (完全不变) ---
def format_days_to_years_days(days):
    if days is None or pd.isna(days): return "N/A"
    try:
        days = int(days); years = days // 365; remaining_days = days % 365
        return f"{years}年, {remaining_days}天" if years > 0 else f"{remaining_days}天"
    except (ValueError, TypeError): return "N/A"

def calculate_unified_age(row):
    if pd.notna(row.get('referring_domains_first_seen_date')):
        try:
            seen_date = pd.to_datetime(row['referring_domains_first_seen_date'])
            now_date = pd.Timestamp.now(tz='UTC')
            if seen_date.tzinfo is None: seen_date = seen_date.tz_localize('UTC')
            return (now_date - seen_date).days
        except (ValueError, TypeError): pass
    if pd.notna(row.get('referring_domains_age_in_days')):
        try: return int(row['referring_domains_age_in_days'])
        except (ValueError, TypeError): pass
    return None

# --- 配置与客户端 (完全不变) ---
st.set_page_config(layout="wide", page_title="外链战略决策平台")
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CSS样式 (OPTIMIZED: 仅保留必要的微调) ---
st.markdown("""
<style>
    /* 侧边栏关键词输入框的标签 */
    label[for="keyword_tags_input-list"] {
        font-size: 0.4rem !important; font-weight: normal !important; color: #a0a4ac !important;
    }
    /* 移除Metric组件和其标签之间的默认大间距，让其更紧凑 */
    [data-testid="stMetric"] > div {
        gap: 0px;
    }
    /* 缩小Metric标签的字体大小 */
    [data-testid="stMetric"] label {
        font-size: 0.8rem;
    }
    /* 移除stForm的边框和内边距 */
    div[data-testid="stForm"] {
        border: none;
        padding: 0;
        margin: 0;
    }
    /* 粗略调整按钮的垂直位置，使其与下拉框对齐 */
    div.stButton {
        padding-top: 28px;
    }
</style>
""", unsafe_allow_html=True)

# --- 数据获取与处理 (完全不变) ---
@st.cache_data(ttl=600)
def get_master_data(website_name=None):
    try:
        # 步骤 1: 获取所有“有价值”的域名
        available_domains_response = supabase.rpc('get_available_domains').select(
            'id, domain_name, da, dr, organic_traffic, first_seen_date, age_in_days, category'
        ).execute()
        
        if not available_domains_response.data:
            st.warning("数据库中没有找到任何符合基本条件的“有价值”域名。")
            return pd.DataFrame()

        domains_df = pd.DataFrame(available_domains_response.data)
        
        if domains_df.empty or 'id' not in domains_df.columns:
            st.info("未能从有价值的域名中获取有效ID。")
            return pd.DataFrame()
            
        domains_df.dropna(subset=['id'], inplace=True)
        domains_df['id'] = domains_df['id'].astype(int)
        
        domains_df.set_index('id', inplace=True)
        available_domain_ids = domains_df.index.tolist()

        if not available_domain_ids:
            st.info("有价值的域名列表为空，无法继续查询报价。")
            return pd.DataFrame()

        # ✨ [核心修复] 实现分块查询 (Chunking)
        all_offers_data = []
        chunk_size = 100  # 每次查询100个ID，这是一个非常安全的大小
        
        for i in range(0, len(available_domain_ids), chunk_size):
            chunk = available_domain_ids[i:i + chunk_size]
            
            offers_response = supabase.table('vendor_offers').select(
                "id, price, vendors(name), rd_id"
            ).in_('rd_id', chunk).eq('status', 'active').execute()
            
            if offers_response.data:
                all_offers_data.extend(offers_response.data)

        if not all_offers_data:
            st.info("找到了有价值的域名，但它们当前没有活跃的报价。")
            return pd.DataFrame()
            
        offers_df = pd.DataFrame(all_offers_data)

        # 步骤 3: 数据合并与处理 (此部分逻辑已验证，保持不变)
        offers_df['domain_name'] = offers_df['rd_id'].map(domains_df['domain_name'])
        offers_df['da'] = offers_df['rd_id'].map(domains_df['da'])
        offers_df['dr'] = offers_df['rd_id'].map(domains_df['dr'])
        offers_df['category'] = offers_df['rd_id'].map(domains_df['category'])
        offers_df['traffic'] = offers_df['rd_id'].map(domains_df['organic_traffic'])
        offers_df['referring_domains_first_seen_date'] = offers_df['rd_id'].map(domains_df['first_seen_date'])
        offers_df['referring_domains_age_in_days'] = offers_df['rd_id'].map(domains_df['age_in_days'])
        
        offers_df['vendor'] = offers_df['vendors'].apply(lambda v: v['name'] if isinstance(v, dict) else None)
        offers_df.rename(columns={'id': 'offer_id'}, inplace=True)

        # --- 后续所有的数据聚合与处理逻辑完全不变 ---
        df = offers_df.copy()
        df['age_in_days'] = df.apply(calculate_unified_age, axis=1)
        
        for col in ['price', 'da', 'dr', 'traffic', 'age_in_days']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df.dropna(subset=['domain_name', 'price', 'vendor'], inplace=True)
        df.sort_values(by=['domain_name', 'price'], inplace=True)
        
        offers_agg = df.groupby('domain_name').apply(lambda x: list(x[['offer_id', 'vendor', 'price']].to_dict('records')), include_groups=False).rename('all_offers')
        base_info_df = df.drop_duplicates(subset='domain_name', keep='first')
        
        # 确保我们要用的列都存在
        required_cols = ['domain_name', 'da', 'dr', 'traffic', 'age_in_days', 'category'] # 明确加入 category
        for col in required_cols:
            if col not in base_info_df.columns:
                # 如果某列意外丢失，填充一个默认值以防报错
                base_info_df[col] = None 
                
        agg_df = base_info_df.set_index('domain_name')
        
        # 只 join offers_agg，保留 agg_df 中已有的所有列
        agg_df = agg_df.join(offers_agg)
        
        agg_df['best_offer_id'] = agg_df['all_offers'].apply(lambda x: x[0]['offer_id'] if x else None)
        agg_df['best_price'] = agg_df['all_offers'].apply(lambda x: x[0]['price'] if x else None)
        agg_df['best_vendor'] = agg_df['all_offers'].apply(lambda x: x[0]['vendor'] if x else None)
        agg_df['num_vendors'] = agg_df['all_offers'].apply(len)

        # --- [核心修复] 根据传入的 website_name 筛选采购历史 ---
        history_query = supabase.table('purchase_history').select('offer_id, vendor_offers(referring_domains(domain_name))')
        
        # 如果提供了网站名称，则增加筛选条件
        if website_name:
            history_query = history_query.eq('website_name_text', website_name)
            
        history_response = history_query.execute()
        cart_response = supabase.table('shopping_cart').select('offer_id, client_websites(name), vendor_offers(referring_domains(domain_name))').execute()
        history_data, cart_data = history_response.data or [], cart_response.data or []
        
        history_domains = [h['vendor_offers']['referring_domains']['domain_name'] for h in history_data if h.get('vendor_offers') and h['vendor_offers'].get('referring_domains')]
        purchase_counts = pd.Series(history_domains).value_counts().to_dict()
        agg_df['total_purchases'] = agg_df.index.map(purchase_counts).fillna(0).astype(int)
        
        cart_map = {}
        for item in cart_data:
            if item.get('vendor_offers') and item['vendor_offers'].get('referring_domains') and item.get('client_websites'):
                domain = item['vendor_offers']['referring_domains']['domain_name']
                site = item['client_websites']['name']
                if domain not in cart_map: cart_map[domain] = set()
                cart_map[domain].add(site)
        agg_df['in_carts_for'] = [list(cart_map.get(domain, set())) for domain in agg_df.index]
        
        return agg_df.reset_index().dropna(subset=['best_price', 'da', 'dr', 'traffic', 'age_in_days'])

    except Exception as e:
        st.error(f"获取主数据时发生严重错误: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_client_websites():
    """获取所有状态为 'active' 的网站列表"""
    try:
        # 在查询中增加 .eq('status', 'active') 过滤条件
        response = supabase.table('client_websites').select('id, name').eq('status', 'active').execute()
        return response.data or []
    except Exception as e:
        st.sidebar.error(f"加载网站列表失败: {e}")
        return []

@st.cache_data(ttl=300)
def get_recently_purchased_domains(website_name, days):
    if not website_name or days <= 0: return set()
    since_date = (datetime.now() - timedelta(days=days)).isoformat()
    try:
        response = supabase.table('purchase_history').select('domain_name_text').eq('website_name_text', website_name).gte('purchase_date', since_date).execute()
        return {item['domain_name_text'] for item in response.data if item.get('domain_name_text')}
    except Exception as e:
        st.sidebar.warning(f"查询采购历史时出错: {e}"); return set()

# --- 主页面逻辑 ---
st.title("💡 外链战略决策平台")

# --- 侧边栏筛选 (完全不变) ---
st.sidebar.title("🎯 筛选条件")
client_websites_list = get_client_websites()
website_options = {site['name']: site['id'] for site in client_websites_list}
selected_site_name = st.sidebar.selectbox("Website", options=list(website_options.keys()), help="选择一个您管理的目标网站。")
master_df = get_master_data(website_name=selected_site_name)
with st.sidebar:
    selected_keywords = st_tags(label='Keyword：', suggestions=['gambling', 'slot', 'poker', 'sports', 'casino', 'bet'], maxtags=10, key='keyword_tags_input')
    price_range = st.slider("Price", 0, 10000, (0, 600), step=50)
    min_score = st.slider("推荐分", 0, 100, 0, help="只显示综合推荐分数高于此值的链接。")
    min_da = st.slider("DA", 0, 100, 0)
    min_dr = st.slider("DR", 0, 100, 0)
    min_age_years = st.slider("Age", 0, 30, 0)
    min_traffic = st.number_input("Organic Traffic", min_value=0, value=0, step=100)
    if not master_df.empty:
        available_vendors = sorted(master_df['best_vendor'].unique())
        selected_vendors = st.multiselect("Vendor", options=available_vendors, help="只显示来自特定供应商的链接。留空则显示所有供应商。")

        # --- 新增 Category 筛选器 ---
        # 首先，我们需要从 master_df 中获取所有唯一的、非空的分类
        # 我们需要一个辅助列来获取原始的 category
        @st.cache_data(ttl=600)
        def get_all_categories():
            # 为了性能，直接从数据库查询所有唯一的分类
            response = supabase.table('referring_domains').select('category').execute()
            if not response.data:
                return []
            # 使用 set 来去重，并过滤掉 None 或空字符串
            categories = {item['category'] for item in response.data if item.get('category')}
            return sorted(list(categories))

        available_categories = get_all_categories()
        selected_categories = st.multiselect("Category", options=available_categories, help="只显示来自特定分类的链接。留空则显示所有分类。")
        # --- 新增结束 ---

    else:
        selected_vendors = st.multiselect("Vendor", [], [], disabled=True)
        # ✨ 在 master_df 为空时，也显示一个禁用的 category 筛选框
        selected_categories = st.multiselect("Category", [], [], disabled=True)
    
    st.markdown("---")
    exclude_days = st.number_input("🚫 排除 N 天内已购域名", min_value=0, value=90, step=10)
    #exclude_blacklist = st.toggle("🚫 Blacklisted Domain", value=True)
    show_only_premium = st.toggle("⭐ Premium Domain", value=False)

# --- 数据筛选与处理 (完全不变) ---
if master_df.empty:
    st.info("数据库中没有可用的报价数据。")
    final_df = pd.DataFrame()
else:
    final_df = master_df.copy()
    
    # --- 价格范围筛选 ---
    def has_offer_in_range(offers_list, min_p, max_p):
        if not isinstance(offers_list, list): return False
        return any(min_p <= offer['price'] <= max_p for offer in offers_list)
    final_df = final_df[final_df.apply(lambda row: has_offer_in_range(row['all_offers'], price_range[0], price_range[1]), axis=1)]
    
    # --- 标记匹配价格的 Offer ---
    def mark_matching_offers(offers_list, min_p, max_p):
        if not isinstance(offers_list, list): return []
        return [{**offer, 'is_match': min_p <= offer['price'] <= max_p} for offer in offers_list]
    if not final_df.empty:
        final_df['display_offers'] = final_df['all_offers'].apply(lambda offers: mark_matching_offers(offers, price_range[0], price_range[1]))
    
    # --- 指标筛选 ---
    final_df = final_df[(final_df['da'] >= min_da) & (final_df['dr'] >= min_dr) & (final_df['traffic'] >= min_traffic)]
    
    # --- 供应商筛选 ---
    if selected_vendors:
        final_df = final_df[final_df['all_offers'].apply(lambda offers: any(offer['vendor'] in selected_vendors for offer in offers))]
        
    # ✨ --- 新增：分类筛选 --- ✨
    if selected_categories:
        # 增加一个安全检查，以防 'category' 列意外丢失
        if 'category' in final_df.columns:
            # .isin() 是处理多选筛选的最佳方式
            final_df = final_df[final_df['category'].isin(selected_categories)]
        else:
            st.warning("警告：无法按分类进行筛选，因为数据中缺少 'category' 列。")
            
    # --- 年龄筛选 ---
    if min_age_years > 0:
        final_df = final_df[final_df['age_in_days'] >= min_age_years * 365]
        
    # --- 关键词筛选 ---
    if selected_keywords:
        regex_pattern = '|'.join(re.escape(kw) for kw in selected_keywords)
        final_df = final_df[final_df['domain_name'].str.contains(regex_pattern, case=False, na=False)]
        
    # --- 排除近期已购域名 ---
    if exclude_days > 0 and selected_site_name:
        with st.spinner(f"正在查找 {selected_site_name} 在 {exclude_days} 天内的购买记录..."):
            recently_purchased = get_recently_purchased_domains(selected_site_name, exclude_days)
        if recently_purchased:
            final_df = final_df[~final_df['domain_name'].isin(recently_purchased)]

# --- 推荐分与Premium逻辑 (完全不变) ---
if not final_df.empty:
    weights = {'da': 0.25, 'dr': 0.25, 'traffic': 0.20, 'age': 0.15, 'price': 0.15}
    scaler = MinMaxScaler()
    score_df = pd.DataFrame(index=final_df.index)
    for col in ['da', 'dr', 'traffic', 'age_in_days', 'best_price']:
        # 增加安全检查，防止列不存在
        if col in final_df.columns:
            if len(final_df[col].unique()) > 1:
                score_df[f'{col}_norm'] = scaler.fit_transform(final_df[[col]]).flatten()
            else:
                score_df[f'{col}_norm'] = 0.5
    
    # 确保所有范化的列都存在
    if all(f'{c}_norm' in score_df.columns for c in ['da', 'dr', 'traffic', 'age_in_days', 'best_price']):
        final_df['recommend_score'] = (
            score_df['da_norm'] * weights['da'] + 
            score_df['dr_norm'] * weights['dr'] + 
            score_df['traffic_norm'] * weights['traffic'] + 
            score_df['age_in_days_norm'] * weights['age'] + 
            (1 - score_df['best_price_norm']) * weights['price']
        )
        if len(final_df['recommend_score'].unique()) > 1:
            final_df['recommend_score'] = scaler.fit_transform(final_df[['recommend_score']]).flatten() * 100
        else:
            final_df['recommend_score'] = 50.0
        
        if min_score > 0:
            final_df = final_df[final_df['recommend_score'] >= min_score]

premium_domains = {item['domain_name'] for item in supabase.table('domain_premiumlist').select('domain_name').execute().data or []}
if not final_df.empty:
    final_df['is_premium'] = final_df['domain_name'].isin(premium_domains)
    if show_only_premium:
        final_df = final_df[final_df['is_premium'] == True]

# --- UI渲染逻辑 ---
if final_df.empty:
    st.info("根据您的筛选条件，没有找到符合的 Backlink 机会。")
else:
    # --- 1. [核心修复] 将辅助函数定义移到最前面 ---
    def format_offers_display(offers_list):
        offers_to_show = offers_list[:2] if isinstance(offers_list, list) else []
        parts = []
        for offer in offers_to_show:
            # 增加对 offer['price'] 的安全检查
            price_text = f"${offer['price']:.2f}" if isinstance(offer.get('price'), (int, float)) else "$ N/A"
            text = f"{offer.get('vendor', 'N/A')}_{price_text}"
            if offer.get('is_match', False):
                parts.append(f"{text}")
            else:
                parts.append(text)
        return " | ".join(parts)

    # --- 2. 准备基础展示列 ---
    final_df['age_formatted'] = final_df['age_in_days'].apply(format_days_to_years_days)
    
    # --- 3. 执行所有筛选 ---
    
    # --- 价格范围筛选 ---
    def has_offer_in_range(offers_list, min_p, max_p):
        if not isinstance(offers_list, list): return False
        return any(min_p <= offer.get('price', -1) <= max_p for offer in offers_list)
    final_df = final_df[final_df.apply(lambda row: has_offer_in_range(row['all_offers'], price_range[0], price_range[1]), axis=1)]
    
    # --- 标记匹配价格的 Offer ---
    def mark_matching_offers(offers_list, min_p, max_p):
        if not isinstance(offers_list, list): return []
        return [{**offer, 'is_match': min_p <= offer.get('price', -1) <= max_p} for offer in offers_list]
    if not final_df.empty:
        final_df['display_offers'] = final_df['all_offers'].apply(lambda offers: mark_matching_offers(offers, price_range[0], price_range[1]))
    
    # --- 指标筛选 ---
    final_df = final_df[(final_df['da'] >= min_da) & (final_df['dr'] >= min_dr) & (final_df['traffic'] >= min_traffic)]
    
    # --- 供应商筛选 ---
    if selected_vendors:
        final_df = final_df[final_df['all_offers'].apply(lambda offers: any(offer['vendor'] in selected_vendors for offer in offers))]
        
    # --- 分类筛选 ---
    if selected_categories:
        if 'category' in final_df.columns:
            final_df = final_df[final_df['category'].isin(selected_categories)]
        else:
            st.warning("警告：无法按分类进行筛选，因为数据中缺少 'category' 列。")
            
    # --- 年龄筛选 ---
    if min_age_years > 0:
        final_df = final_df[final_df['age_in_days'] >= min_age_years * 365]
        
    # --- 关键词筛选 ---
    if selected_keywords:
        regex_pattern = '|'.join(re.escape(kw) for kw in selected_keywords)
        final_df = final_df[final_df['domain_name'].str.contains(regex_pattern, case=False, na=False)]
        
    # --- 排除近期已购域名 ---
    if exclude_days > 0 and selected_site_name:
        with st.spinner(f"正在查找 {selected_site_name} 在 {exclude_days} 天内的购买记录..."):
            recently_purchased = get_recently_purchased_domains(selected_site_name, exclude_days)
        if recently_purchased:
            final_df = final_df[~final_df['domain_name'].isin(recently_purchased)]

    # --- 4. 在所有筛选后，重新检查DataFrame是否为空 ---
    if final_df.empty:
        st.info("根据您的筛选条件，没有找到符合的 Backlink 机会。")
        st.stop()

    # --- 5. 计算推荐分与处理Premium ---
    weights = {'da': 0.25, 'dr': 0.25, 'traffic': 0.20, 'age': 0.15, 'price': 0.15}
    scaler = MinMaxScaler()
    score_df = pd.DataFrame(index=final_df.index)
    for col in ['da', 'dr', 'traffic', 'age_in_days', 'best_price']:
        if col in final_df.columns:
            if len(final_df[col].unique()) > 1:
                score_df[f'{col}_norm'] = scaler.fit_transform(final_df[[col]]).flatten()
            else:
                score_df[f'{col}_norm'] = 0.5
    
    if all(f'{c}_norm' in score_df.columns for c in ['da', 'dr', 'traffic', 'age_in_days', 'best_price']):
        final_df['recommend_score'] = (
            score_df['da_norm'] * weights['da'] + 
            score_df['dr_norm'] * weights['dr'] + 
            score_df['traffic_norm'] * weights['traffic'] + 
            score_df['age_in_days_norm'] * weights['age'] + 
            (1 - score_df['best_price_norm']) * weights['price']
        )
        if len(final_df['recommend_score'].unique()) > 1:
            final_df['recommend_score'] = scaler.fit_transform(final_df[['recommend_score']]).flatten() * 100
        else:
            final_df['recommend_score'] = 50.0
        
        if min_score > 0:
            final_df = final_df[final_df['recommend_score'] >= min_score]

    premium_domains = {item['domain_name'] for item in supabase.table('domain_premiumlist').select('domain_name').execute().data or []}
    final_df['is_premium'] = final_df['domain_name'].isin(premium_domains)
    if show_only_premium:
        final_df = final_df[final_df['is_premium'] == True]

    # --- 6. 再次检查DataFrame是否为空并准备最终展示列 ---
    if final_df.empty:
        st.info("根据您的筛选条件，没有找到符合的 Backlink 机会。")
        st.stop()
        
    final_df['display_domain'] = final_df.apply(lambda row: f"⭐ {row['domain_name']}" if row['is_premium'] else row['domain_name'], axis=1)
    final_df['offers_display'] = final_df['display_offers'].apply(format_offers_display)

    # --- 7. 排序 ---
    sort_mapping = {
        "推荐分": "recommend_score", "最低价格": "best_price", "DA": "da", "DR": "dr",
        "流量": "traffic", "年龄": "age_in_days", "总购买次数": "total_purchases", "供应商数量": "num_vendors"
    }
    sort_options_display = list(sort_mapping.keys())
    is_ascending = st.session_state.sort_by == 'best_price'
    display_df = final_df.sort_values(by=[st.session_state.sort_by], ascending=is_ascending, kind="mergesort", na_position='last')

    # --- 8. 准备 data_editor 的 DataFrame ---
    display_df['select_1'] = False
    display_df['select_2'] = False
    for index, row in display_df.iterrows():
        domain = row['domain_name']
        if domain in st.session_state.selections:
            selected_offer_id = st.session_state.selections[domain]
            offers = row['display_offers']
            if len(offers) > 0 and offers[0]['offer_id'] == selected_offer_id: display_df.loc[index, 'select_1'] = True
            if len(offers) > 1 and offers[1]['offer_id'] == selected_offer_id: display_df.loc[index, 'select_2'] = True
    
    editor_df = pd.DataFrame({
        "🛒 1": display_df['select_1'], "🛒 2": display_df['select_2'],
        "推荐分": display_df['recommend_score'], "最低价格": display_df['best_price'],
        "域名": display_df['display_domain'], "分类": display_df['category'],
        "供应商 & 价格": display_df['offers_display'], "供应商数量": display_df['num_vendors'],
        "DA": display_df['da'], "DR": display_df['dr'], "流量": display_df['traffic'],
        "年龄": display_df['age_formatted'], "总购买次数": display_df['total_purchases'],
        "已在购物车": display_df['in_carts_for'], "_domain_name": display_df['domain_name'],
        "_offers": display_df['display_offers']
    })

    # --- 9. 渲染UI ---
    st.markdown("---")
    
    with st.form("editor_form"):
        cols = st.columns([1, 0.5, 0.5, 3, 1.5, 2])

        with cols[0]:
            selected_display_sort = st.selectbox(
                "排序方式", sort_options_display,
                index=sort_options_display.index([k for k, v in sort_mapping.items() if v == st.session_state.sort_by][0]),
                label_visibility="collapsed"
            )
            if sort_mapping[selected_display_sort] != st.session_state.sort_by:
                st.session_state.sort_by = sort_mapping[selected_display_sort]
                st.rerun()
        
        with cols[1]:
            submitted = st.form_submit_button("✅ Apply", width='stretch')
        with cols[2]:
            clear_clicked = st.form_submit_button("🗑️ Clear", width='stretch', help="清空所有勾选")

        total_cart_count = len(st.session_state.selections)
        total_cart_price = 0
        if total_cart_count > 0:
            selected_offer_ids = list(st.session_state.selections.values())
            all_selected_offers_df = master_df[master_df['all_offers'].apply(lambda offers: any(o['offer_id'] in selected_offer_ids for o in offers))]
            for _, row in all_selected_offers_df.iterrows():
                for offer in row['all_offers']:
                    if offer['offer_id'] in selected_offer_ids:
                        total_cart_price += offer['price']
                        break
        
        with cols[4]:
            st.metric(label="🔍 域名", value=f"{len(display_df)}")
        with cols[5]:
            st.metric(label="🛒 购物车", value=f"${total_cart_price:,.2f}", delta=f"{total_cart_count} 个链接" if total_cart_count > 0 else None)
        st.markdown("---")
        
        edited_df = st.data_editor(
            editor_df, key="offers_editor",
            column_config={
                "🛒 1": st.column_config.CheckboxColumn(help="选择第一个供应商"),
                "🛒 2": st.column_config.CheckboxColumn(help="选择第二个供应商"),
                "推荐分": st.column_config.ProgressColumn("推荐分", format="%d", min_value=0, max_value=100),
                "最低价格": st.column_config.NumberColumn("最低价格 ($)", format="$ %.2f"),
                "供应商 & 价格": st.column_config.TextColumn("供应商 & 价格"),
                "流量": st.column_config.NumberColumn(format="%d"),
                "分类": st.column_config.TextColumn("分类"),
                "已在购物车": st.column_config.ListColumn("已在购物车")
            },
            disabled=editor_df.columns.drop(["🛒 1", "🛒 2"]), hide_index=True, width='stretch', height=850,
            column_order=[col for col in editor_df.columns if not col.startswith('_') and col != '最低价格']
        )

    # --- 5. 处理按钮逻辑 ---
    if clear_clicked:
        st.session_state.selections = {}
        st.toast("🛒 购物车已清空！")
        st.rerun()

    if submitted:
        new_selections = {}
        for _, row in edited_df.iterrows():
            domain = row['_domain_name']
            offers = row['_offers'] or []
            if row.get('🛒 2', False) and len(offers) > 1:
                new_selections[domain] = offers[1]['offer_id']
            elif row.get('🛒 1', False) and len(offers) > 0:
                new_selections[domain] = offers[0]['offer_id']
        st.session_state.selections = new_selections
        st.toast("✔️ 已更新勾选！")
        st.rerun()
    
    # --- 6. 采购计划逻辑 ---
    if total_cart_count > 0:
        # 复用上面计算好的 total_cart_price 和 selected_offer_ids
        purchase_plan_data = []
        all_selected_offers_df = master_df[master_df['all_offers'].apply(lambda offers: any(o['offer_id'] in selected_offer_ids for o in offers))].copy()
        for _, row in all_selected_offers_df.iterrows():
            for offer in row['all_offers']:
                if offer['offer_id'] in selected_offer_ids:
                    purchase_plan_data.append({'domain_name': row['domain_name'], 'vendor': offer['vendor'], 'price': offer['price'], 'offer_id': offer['offer_id']})
                    break
        purchase_plan_df = pd.DataFrame(purchase_plan_data)

        st.markdown("---")
        st.header("📋 第二步: 生成采购计划")
        vendor_groups = purchase_plan_df.groupby('vendor')
        st.info(f"您已选择 **{len(purchase_plan_df)}** 个链接，预估总花费 **${total_cart_price:,.2f}**。将从 **{len(vendor_groups)}** 个供应商处采购。")
        for vendor, group in vendor_groups:
            with st.expander(f"**{vendor}** (采购: {len(group)} 个链接 | 花费: ${group['price'].sum():,.2f})"):
                st.dataframe(group[['domain_name', 'price']].rename(columns={'domain_name': '域名', 'price': '价格'}), hide_index=True, width='stretch')
        if st.button(f"✅ 确认并将这 {len(purchase_plan_df)} 个链接加入 **{selected_site_name}** 的购物车", type="primary", width='stretch'):
            if selected_site_name and (selected_site_id := website_options.get(selected_site_name)):
                cart_items = [{'offer_id': int(oid), 'website_id': selected_site_id} for oid in purchase_plan_df['offer_id']]
                try:
                    supabase.table('shopping_cart').upsert(cart_items, on_conflict='offer_id, website_id').execute()
                    st.success(f"✅ 成功将 {len(cart_items)} 个链接加入购物车！"); st.balloons()
                    st.session_state.selections = {}; st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"加入购物车失败: {e}")
            else:
                st.error("请先在侧边栏选择一个有效的网站！")