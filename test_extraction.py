#!/usr/bin/env python3

import json
import re

def extract_html_from_markdown(text: str) -> str:
    """
    Trích xuất HTML từ markdown code block.
    Tìm ```html...``` hoặc ````html...```` và lấy nội dung bên trong.
    """
    if not isinstance(text, str):
        return ""
    
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

def extract_html(result):
    """Test the extraction function with the actual output format"""
    if not result:
        return ""
    
    # các đường dẫn phổ biến
    candidates = [
        ("data", "outputs", "html"),
        ("data", "outputs", "output"),  # This is the correct path for your data
        ("data", "output"),
        ("data",),
        ("output_text",),
        ("outputs", "html"),
        ("html",),
        ("output",),
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
            print(f"Found content at path: {' -> '.join(path)}")
            print(f"Content starts with: {val[:100]}...")
            
            # Thử trích xuất HTML từ markdown trước
            html_from_markdown = extract_html_from_markdown(val)
            if html_from_markdown:
                print(f"Successfully extracted HTML ({len(html_from_markdown)} characters)")
                return html_from_markdown
            # Nếu không phải markdown, kiểm tra xem có phải HTML thô không
            if '<html' in val.lower() or '<!doctype html' in val.lower():
                print("Found raw HTML")
                return val
            else:
                print("Content found but not HTML format")
    
    return ""

# Test with the actual output.json data
if __name__ == "__main__":
    with open('/home/thanhkt/CODE/demo_dify/output.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("Testing HTML extraction...")
    html = extract_html(data)
    
    if html:
        print(f"✅ SUCCESS: Extracted HTML with {len(html)} characters")
        print(f"HTML starts with: {html[:200]}...")
        print(f"HTML ends with: ...{html[-200:]}")
    else:
        print("❌ FAILED: Could not extract HTML")
        print("Available keys at data.outputs:", list(data.get('data', {}).get('outputs', {}).keys()))
