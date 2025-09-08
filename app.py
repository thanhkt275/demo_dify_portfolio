import os
import json
import requests
import streamlit as st
import base64
import uuid
from datetime import datetime
from typing import Dict, Any
import tempfile

# 1x1 transparent PNG (base64)
_BLANK_FAVICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/aoGxX8AAAAASUVORK5CYII="
try:
    _blank_favicon = base64.b64decode(_BLANK_FAVICON_B64)
except Exception:
    _blank_favicon = None

st.set_page_config(
    page_title="Portfolio Generator via Dify",
    page_icon=_blank_favicon,  # neutral favicon (no icon)
    layout="wide",
)

# ===== Helpers =====
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)

DIFY_API_KEY = get_secret("DIFY_API_KEY")
BASE_URL     = get_secret("BASE_URL", "https://api.dify.ai").rstrip("/")
WORKFLOW_ID  = get_secret("WORKFLOW_ID", "")  # dùng nếu endpoint cần
# HTTP timeout (seconds) for blocking workflow run
try:
    HTTP_TIMEOUT = int(get_secret("HTTP_TIMEOUT", "180"))  # default 180s
except Exception:
    HTTP_TIMEOUT = 180

def call_dify_workflow(inputs: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Gọi Dify Workflows (blocking) trả về kết quả ngay.
    Hai biến thể phổ biến của endpoint (tùy phiên bản Dify bạn dùng):
    1) POST {BASE_URL}/v1/workflows/run
       body: {"workflow_id": "...", "inputs": {...}, "response_mode": "blocking", "user": "..."}
    2) POST {BASE_URL}/v1/workflows/{workflow_id}/run
       body: {"inputs": {...}, "response_mode": "blocking", "user": "..."}

    Hàm này thử #2 trước (nếu có WORKFLOW_ID); nếu lỗi 404 sẽ fallback sang #1.
    """
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }

    # Nếu có WORKFLOW_ID -> thử variant /v1/workflows/{id}/run
    if WORKFLOW_ID:
        url = f"{BASE_URL}/v1/workflows/{WORKFLOW_ID}/run"
        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user_id or "anonymous"
        }
        try:
            # use tuple: (connect timeout, read timeout)
            resp = requests.post(url, headers=headers, json=payload, timeout=(15, HTTP_TIMEOUT))
        except requests.Timeout:
            return {"status_code": 408, "json": {"error": "request_timeout", "message": f"Workflow exceeded timeout of {HTTP_TIMEOUT}s"}}
        except requests.RequestException as e:
            return {"status_code": 0, "json": {"error": "request_error", "message": str(e)}}
        # Nếu server không biết endpoint này, thử fallback
        if resp.status_code != 404:
            return {"status_code": resp.status_code, "json": safe_json(resp)}

    # Fallback: /v1/workflows/run kèm workflow_id
    url = f"{BASE_URL}/v1/workflows/run"
    payload = {
        "workflow_id": WORKFLOW_ID or inputs.get("sys.workflow_id") or "",
        "inputs": inputs,
        "response_mode": "blocking",
        "user": user_id or "anonymous"
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=(15, HTTP_TIMEOUT))
        return {"status_code": resp.status_code, "json": safe_json(resp)}
    except requests.Timeout:
        return {"status_code": 408, "json": {"error": "request_timeout", "message": f"Workflow exceeded timeout of {HTTP_TIMEOUT}s"}}
    except requests.RequestException as e:
        return {"status_code": 0, "json": {"error": "request_error", "message": str(e)}}

def safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"raw_text": resp.text}

def create_shareable_link(html_content: str) -> str:
    """
    Create a shareable link by encoding HTML content in base64
    This allows users to share portfolios without needing a server
    """
    encoded_html = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    return f"data:text/html;base64,{encoded_html}"

def render_open_new_tab_button(html_content: str, label: str = "Open Preview in New Tab") -> None:
    """Render a client-side button that opens the HTML in a new tab via Blob.
    This avoids browser restrictions that sometimes show about:blank for data: URLs.
    """
    try:
        b64 = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    except Exception:
        b64 = ""
    btn_id = f"open-new-tab-{uuid.uuid4().hex[:8]}"
    st.components.v1.html(
        f"""
        <button id="{btn_id}" style="display:inline-block;padding:0.5rem 0.75rem;border:1px solid #ddd;border-radius:8px;background:#fff;cursor:pointer;margin-bottom:0.5rem;">{label}</button>
        <script>
        (function(){{
            const b64 = "{b64}";
            const toBlob = (b64str) => {{
                if (!b64str) return new Blob([""], {{type: 'text/html'}});
                const byteChars = atob(b64str);
                const byteNums = new Array(byteChars.length);
                for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i);
                return new Blob([new Uint8Array(byteNums)], {{type: 'text/html'}});
            }};
            const blob = toBlob(b64);
            const btn = document.getElementById('{btn_id}');
            if (btn) {{
                btn.addEventListener('click', function() {{
                    const url = URL.createObjectURL(blob);
                    const w = window.open(url, '_blank');
                    if (!w) {{
                        alert('Please allow pop-ups to open the preview.');
                    }}
                    setTimeout(() => URL.revokeObjectURL(url), 60000);
                }});
            }}
        }})();
        </script>
        """,
        height=60,
    )

def save_to_session_state(html_content: str, user_inputs: Dict[str, Any]) -> str:
    """Save generated HTML to session state with unique ID for sharing"""
    if 'portfolios' not in st.session_state:
        st.session_state.portfolios = {}
    
    portfolio_id = str(uuid.uuid4())[:8]
    st.session_state.portfolios[portfolio_id] = {
        'html': html_content,
        'inputs': user_inputs,
        'created_at': datetime.now().isoformat(),
        'title': f"{user_inputs.get('full_name', 'Portfolio')} - {user_inputs.get('job_title', 'Professional')}"
    }
    return portfolio_id

def get_html_preview_component(html_content: str, height: int = 600) -> None:
    """Enhanced HTML preview component with click prevention and error handling"""
    if not html_content.strip():
        st.warning("No HTML content to preview")
        return
    
    # Add responsive meta tag if not present
    if 'viewport' not in html_content:
        html_content = html_content.replace(
            '<head>',
            '<head>\n<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        )
    
    # More robust click prevention script
    click_prevention_script = """
    <script>
        // Prevent all navigation and interactions
        function preventDefaultBehavior(e) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }
        
        function setupPreventionHandlers() {
            // Prevent all form submissions
            document.querySelectorAll('form').forEach(function(form) {
                form.addEventListener('submit', preventDefaultBehavior);
            });
            
            // Handle all links
            document.querySelectorAll('a').forEach(function(link) {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const href = link.href;
                    if (href && href.startsWith('mailto:')) {
                        // Allow mailto links
                        window.open(href, '_blank');
                    } else if (href && (href.startsWith('tel:') || href.startsWith('phone:'))) {
                        // Allow phone links
                        window.open(href, '_blank');
                    } else if (href && (href.startsWith('http') || href.startsWith('https'))) {
                        // External links - open in new tab
                        window.open(href, '_blank');
                    } else {
                        // Show info for other links
                        console.log('Link navigation prevented in preview mode:', href || link.textContent);
                    }
                    return false;
                });
                
                // Also prevent default link behavior
                link.style.cursor = 'pointer';
            });
            
            // Prevent button interactions
            document.querySelectorAll('button, input[type="submit"], input[type="button"]').forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('Button interaction prevented in preview mode');
                    return false;
                });
            });
            
            // Disable form inputs
            document.querySelectorAll('input:not([type="button"]):not([type="submit"]), textarea, select').forEach(function(input) {
                input.addEventListener('focus', function(e) {
                    e.target.blur();
                });
                input.addEventListener('click', preventDefaultBehavior);
                input.style.cursor = 'not-allowed';
                input.title = 'Form inputs disabled in preview mode';
            });
            
            // Prevent context menu
            document.addEventListener('contextmenu', preventDefaultBehavior);
            
            // Prevent drag and drop
            document.addEventListener('dragstart', preventDefaultBehavior);
            document.addEventListener('drop', preventDefaultBehavior);
        }
        
        // Setup handlers when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupPreventionHandlers);
        } else {
            setupPreventionHandlers();
        }
        
        // Also setup with a small delay to catch dynamically added elements
        setTimeout(setupPreventionHandlers, 100);
    </script>
    """
    
    # Inject the script before closing body tag or at the end
    if '</body>' in html_content:
        html_content = html_content.replace('</body>', f'{click_prevention_script}\n</body>')
    elif '</html>' in html_content:
        html_content = html_content.replace('</html>', f'{click_prevention_script}\n</html>')
    else:
        html_content += click_prevention_script
    
    try:
        # Use Streamlit's HTML component with additional security
        st.components.v1.html(
            html_content, 
            height=height, 
            scrolling=True,
        )
    except Exception as e:
        st.error(f"Error rendering HTML preview: {str(e)}")
        with st.expander("View raw HTML content"):
            st.code(html_content, language='html')

def extract_html(result: Dict[str, Any]) -> str:
    """
    Output
    - {"data": {"outputs": {"html": "<...>"}}}
    - hoặc {"data": {"output": "<...>"}} / {"data": "<...>"} / {"output_text": "<...>"}
    - hoặc text có chứa markdown code block ```html...```
    Hàm này quét các nơi hay gặp để lấy HTML.
    """
    if not result:
        return ""
    
    def extract_html_from_markdown(text: str) -> str:
        """
        Trích xuất HTML từ markdown code block.
        Tìm ```html...``` hoặc ````html...```` và lấy nội dung bên trong.
        """
        if not isinstance(text, str):
            return ""
        
        import re
        # Tìm code block html với ít nhất 3 backticks
        patterns = [
            r'```+html\s*\n(.*?)```+',  # ```html hoặc ````html
            r'```+\s*\n<!DOCTYPE html(.*?)```+',  # ```\n<!DOCTYPE html (trường hợp không có label html)
            r'```+\s*\n<html(.*?)```+',  # ```\n<html
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            if matches:
                html_content = matches[0].strip()
                # Nếu match đầu tiên không phải là HTML hoàn chỉnh, thử ghép lại
                if pattern != r'```+html\s*\n(.*?)```+':
                    if pattern == r'```+\s*\n<!DOCTYPE html(.*?)```+':
                        html_content = "<!DOCTYPE html" + html_content
                    elif pattern == r'```+\s*\n<html(.*?)```+':
                        html_content = "<html" + html_content
                
                # Kiểm tra xem có phải HTML hợp lệ không
                if html_content and ('<html' in html_content.lower() or '<!doctype html' in html_content.lower()):
                    return html_content
        
        return ""
    
    # các đường dẫn phổ biến
    candidates = [
        ("data", "outputs", "output"),  # Dify (new) common
        ("data", "outputs", "html"),
        ("data", "outputs", "output_text"),
        ("data", "output"),
        ("data", "answer"),
        ("data", "text"),
        ("data",),
        ("output_text",),
        ("outputs", "html"),
        ("html",),
        ("output",),  # thêm output trực tiếp
        ("raw_text",),  # from safe_json fallback
        ("result",),
    ]
    
    def deep_get(d, path):
        cur = d
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return None
        return cur

    for path in candidates:
        val = deep_get(result, path)
        if isinstance(val, str) and len(val.strip()) > 0:
            # Thử trích xuất HTML từ markdown trước
            html_from_markdown = extract_html_from_markdown(val)
            if html_from_markdown:
                return html_from_markdown
            # Nếu không phải markdown, kiểm tra xem có phải HTML thô không
            if '<html' in val.lower() or '<!doctype html' in val.lower():
                return val

    # Nếu Dify trả danh sách events (stream đã gom), lấy phần text cuối
    if isinstance(result, dict) and "events" in result and isinstance(result["events"], list):
        texts = [e.get("data", {}).get("text", "") for e in result["events"] if isinstance(e, dict)]
        texts = [t for t in texts if isinstance(t, str) and t.strip()]
        if texts:
            # Thử trích xuất từ text cuối cùng
            html_from_markdown = extract_html_from_markdown(texts[-1])
            if html_from_markdown:
                return html_from_markdown
            # Hoặc ghép tất cả text lại và thử trích xuất
            combined_text = "\n".join(texts)
            html_from_markdown = extract_html_from_markdown(combined_text)
            if html_from_markdown:
                return html_from_markdown
            return texts[-1]
    # Fallback: recursive scan for any string containing HTML or markdown code block
    visited = set()

    def scan(obj) -> str:
        oid = id(obj)
        if oid in visited:
            return ""
        visited.add(oid)
        try:
            if isinstance(obj, dict):
                for v in obj.values():
                    found = scan(v)
                    if found:
                        return found
            elif isinstance(obj, list):
                for v in obj:
                    found = scan(v)
                    if found:
                        return found
            elif isinstance(obj, str):
                s = obj.strip()
                if not s:
                    return ""
                html_from_md = extract_html_from_markdown(s)
                if html_from_md:
                    return html_from_md
                if '<html' in s.lower() or '<!doctype html' in s.lower():
                    return s
                # If it looks like JSON string, try parse once
                if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
                    try:
                        parsed = json.loads(s)
                        return scan(parsed)
                    except Exception:
                        return ""
        except Exception:
            return ""
        return ""

    fallback = scan(result)
    if isinstance(fallback, str) and fallback:
        return fallback

    return ""

# ===== UI =====
# Custom CSS for professional look and to hide Streamlit chrome (menu/header/footer)
st.markdown("""
<style>
    /* Hide Streamlit default chrome */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none !important;}

    /* Tidy buttons */
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #ddd;
        transition: all 0.2s ease-in-out;
        background: #fff;
    }
    .stButton > button:hover {
        border-color: #999;
        color: #111;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }

    /* Subtle containers */
    .success-message {
        padding: 1rem;
        border-radius: 8px;
        background-color: #f1f8f4;
        color: #0f5132;
        border: 1px solid #cfe3d6;
    }
    .portfolio-card {
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e6e6e6;
        margin: 0.5rem 0;
        background: #fff;
    }

    /* Status badges (used if needed) */
    .status-badge { padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.875rem; font-weight: 500; }
    .status-success { background-color: #e8f5e9; color: #2e7d32; }
    .status-error   { background-color: #ffebee; color: #c62828; }
    .status-warning { background-color: #fff8e1; color: #ef6c00; }

    /* Reduce top/bottom padding slightly */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

st.title("AI Portfolio Generator")
st.markdown("Fill your details, generate via Dify, preview and download.")

# Minimal sidebar: only show a reminder if missing API key
with st.sidebar:
    if not DIFY_API_KEY:
        st.warning("Please configure `DIFY_API_KEY` in `.streamlit/secrets.toml`.")

# Load portfolio data if selected from history
default_values = {
    "full_name": "Trần Khánh Thành",
    "job_title": "Software Engineer", 
    "email": "thanhkt27507@gmail.com",
    "phone": "0364491720",
    "location": "Ha Noi",
    "birth": "2007",
    "experience_years": "5",
    "about_me": "I will study in Vin University , Electrical and Computer Engineering Major",
    "skills": "Python, C++, Langchain",
    "education": "Vin Univeristy",
    "social_links": "github.com"
}

# No history loading in simplified UI

with st.form("portfolio_form"):
    col1, col2 = st.columns(2)
    with col1:
        full_name = st.text_input("Họ và tên", value=default_values["full_name"])
        job_title = st.text_input("Chức danh", value=default_values["job_title"])
        email = st.text_input("Email", value=default_values["email"])
        phone = st.text_input("Số điện thoại", value=default_values["phone"])
        location = st.text_input("Địa điểm", value=default_values["location"])
        birth = st.text_input("Năm sinh", value=default_values["birth"])
        experience_years = st.text_input("Số năm kinh nghiệm", value=default_values["experience_years"])
    with col2:
        about_me = st.text_area("Giới thiệu", height=120, value=default_values["about_me"])
        skills = st.text_input("Kỹ năng (phân tách bằng dấu phẩy)", value=default_values["skills"])
        education = st.text_input("Học vấn", value=default_values["education"])
        social_links = st.text_input("Liên kết mạng xã hội", value=default_values["social_links"])

    user_id = st.text_input("User ID", value="3a469858-bd0a-4800-97e7-c572d7bbb759")
    submitted = st.form_submit_button("Generate HTML via Dify", use_container_width=True)

# ===== Submit =====
if submitted:
    if not DIFY_API_KEY:
        st.error("Thiếu DIFY_API_KEY. Vui lòng cấu hình trong secrets.")
        st.stop()

    # Chuẩn hoá inputs theo ví dụ bạn đưa:
    inputs = {
        "full_name": full_name.strip(),
        "job_title": job_title.strip(),
        "about_me": about_me.strip(),
        "skills": skills.strip(),
        "email": email.strip(),
        "phone": phone.strip(),
        "location": location.strip(),
        "birth": birth.strip(),
        "experience_years": experience_years.strip(),
        "education": education.strip(),
        "social_links": social_links.strip(),
        # Nếu workflow của bạn có sử dụng các sys.* thì có thể truyền thêm:
        # "sys.files": [],  # ở dưới có ví dụ chuyển file -> base64/URL nếu cần
        # "sys.app_id": "...",
        # "sys.workflow_id": WORKFLOW_ID or "..."
    }

    # Đính kèm file nếu workflow cần (minh hoạ: đọc bytes -> base64)
    # Nhiều workflow của Dify đọc file từ "sys.files" theo dạng URL; nếu bạn cần upload lên storage khác rồi truyền URL.
    # Ở đây chỉ demo cách đưa metadata về file; điều chỉnh theo node đọc file của bạn.
    # Simple mode: no file attachments

    with st.spinner(f"Đang gọi Dify workflow (blocking) – tối đa ~{HTTP_TIMEOUT}s"):
        BASE_URL = get_secret("BASE_URL", "https://api.dify.ai").rstrip("/")
        result = call_dify_workflow(inputs, user_id=user_id)

    status = result.get("status_code", 0)
    payload = result.get("json", {})

    # Cố gắng lấy HTML từ payload
    html = extract_html(payload)
    
    # Simplified result: only Preview and Download
    if html:
        st.markdown("### Preview")
        # Robust new-tab open using a Blob (works even when data: URLs are blocked)
        render_open_new_tab_button(html, label="Open Preview in New Tab")
        get_html_preview_component(html, height=600)

        st.download_button(
            "Download Code",
            data=html.encode("utf-8"),
            file_name=f"portfolio_{full_name.replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            use_container_width=True
        )
    else:
        st.error("Không tìm thấy HTML content trong phản hồi từ API")
        with st.expander("Xem phản hồi thô để debug"):
            st.json(payload)

# (Tips removed to keep UI minimal)
