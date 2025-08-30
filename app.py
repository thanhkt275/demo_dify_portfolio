import os
import json
import requests
import streamlit as st
from typing import Dict, Any

st.set_page_config(page_title="Portfolio Generator via Dify", page_icon="🧩", layout="wide")

# ===== Helpers =====
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)

DIFY_API_KEY = get_secret("DIFY_API_KEY")
BASE_URL     = get_secret("BASE_URL", "https://api.dify.ai").rstrip("/")
WORKFLOW_ID  = get_secret("WORKFLOW_ID", "")  # dùng nếu endpoint cần

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
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
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
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    return {"status_code": resp.status_code, "json": safe_json(resp)}

def safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"raw_text": resp.text}

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
        ("data", "outputs", "output"),  # Đường dẫn chính cho format Dify mới
        ("data", "outputs", "html"),
        ("data", "output"),
        ("data",),
        ("output_text",),
        ("outputs", "html"),
        ("html",),
        ("output",),  # thêm output trực tiếp
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
    
    return ""

# ===== UI =====
st.title("🧩 Portfolio Generator (Dify Workflow + Streamlit)")
st.write("Điền thông tin cá nhân, gửi qua Dify Workflow để sinh **HTML portfolio**, và xem kết quả ngay bên dưới.")

with st.sidebar:
    st.subheader("⚙️ Cấu hình")
    if not DIFY_API_KEY:
        st.warning("Bạn chưa cấu hình `DIFY_API_KEY` trong secrets. Vui lòng thêm trước khi chạy.")
    st.text_input("BASE_URL", value=BASE_URL, help="URL server của Dify (mặc định https://api.dify.ai)", key="base_url_disabled", disabled=True)
    st.text_input("WORKFLOW_ID (tùy chọn)", value=WORKFLOW_ID, key="wf_id_disabled", disabled=True)
    st.info("Bạn có thể thay đổi trong `.streamlit/secrets.toml`.")

with st.form("portfolio_form"):
    col1, col2 = st.columns(2)
    with col1:
        full_name = st.text_input("Họ và tên", value="Trần Khánh Thành")
        job_title = st.text_input("Chức danh", value="Software Engineer")
        email = st.text_input("Email", value="thanhkt27507@gmail.com")
        phone = st.text_input("Số điện thoại", value="0364491720")
        location = st.text_input("Địa điểm", value="Ha Noi")
        birth = st.text_input("Năm sinh", value="2007")
        experience_years = st.text_input("Số năm kinh nghiệm", value="5")
    with col2:
        about_me = st.text_area("Giới thiệu", height=120, value="I will study in Vin University , Electrical and Computer Engineering Major")
        skills = st.text_input("Kỹ năng (phân tách bằng dấu phẩy)", value="Python, C++, Langchain")
        education = st.text_input("Học vấn", value="Vin Univeristy")
        social_links = st.text_input("Liên kết mạng xã hội", value="github.com")

    # (Tùy chọn) upload file nếu workflow có node đọc file
    uploaded_files = st.file_uploader("Đính kèm tệp (tùy chọn)", type=["pdf", "png", "jpg", "jpeg", "txt", "md"], accept_multiple_files=True)

    user_id = st.text_input("User ID", value="3a469858-bd0a-4800-97e7-c572d7bbb759")
    submitted = st.form_submit_button("🚀 Generate HTML via Dify", use_container_width=True)

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
    sys_files = []
    for f in uploaded_files or []:
        sys_files.append({"name": f.name, "size": f.size, "mime": f.type})
    if sys_files:
        inputs["sys.files"] = sys_files

    with st.spinner("Đang gọi Dify workflow (blocking)…"):
        BASE_URL = get_secret("BASE_URL", "https://api.dify.ai").rstrip("/")
        result = call_dify_workflow(inputs, user_id=user_id)

    status = result.get("status_code", 0)
    payload = result.get("json", {})

    colA, colB = st.columns([2, 1])
    with colB:
        st.markdown("### Trạng thái")
        st.code(status)
        st.markdown("### Phản hồi thô")
        st.json(payload)

    # Cố gắng lấy HTML từ payload
    html = extract_html(payload)
    with colA:
        st.markdown("### 🔧 Kết quả HTML")
        if html:
            # render ngay trong trang
            st.components.v1.html(html, height=900, scrolling=True)
            # Cho phép tải file HTML
            st.download_button(
                "⬇️ Tải về portfolio.html",
                data=html.encode("utf-8"),
                file_name="portfolio.html",
                mime="text/html",
                use_container_width=True
            )
        else:
            st.warning("Không tìm thấy chuỗi HTML trong phản hồi. Hãy kiểm tra cấu hình node output của Workflow.")

# ===== Tips =====
with st.expander("💡 Gợi ý cấu hình Workflow trong Dify"):
    st.markdown(
        """
- Ở node **Start**, định nghĩa các **inputs**: `full_name`, `job_title`, `about_me`, `skills`, `email`, `phone`, `location`, `birth`, `experience_years`, `education`, `social_links`.
- Ở node **LLM / Code / Tool** sinh ra chuỗi **HTML** hoàn chỉnh (bao gồm `<html>…</html>`).
- Ở node **End**, đặt một biến output (ví dụ `html`) chứa chuỗi HTML đó, để API có thể trả về dạng `{"data": {"outputs": {"html": "<…>"}}}`.
- Dùng **response_mode = "blocking"** trong API để Streamlit chờ đủ HTML rồi render.
- Nếu self-host, kiểm tra CORS/Firewall cho endpoint `/v1/workflows/run` hoặc `/v1/workflows/{id}/run`.
        """
    )
