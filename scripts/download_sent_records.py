"""
从 GitHub API 下载 sent_records.json 和 company_detail_cache.json
"""
import os
import sys
import json
import base64

repo = os.environ.get("GITHUB_REPOSITORY", "ArnoHu0201/hongshan-vc-monitor")
token = os.environ.get("GITHUB_TOKEN", "")

headers = {"Authorization": f"token {token}"} if token else {}

files = ["sent_records.json", "company_detail_cache.json"]
output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
os.makedirs(output_dir, exist_ok=True)

for fname in files:
    url = f"https://api.github.com/repos/{repo}/contents/output/{fname}"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if "content" in data:
                content = base64.b64decode(data["content"]).decode("utf-8")
                fpath = os.path.join(output_dir, fname)
                with open(fpath, "w") as f:
                    f.write(content)
                print(f"✓ {fname} 已下载")
            else:
                print(f"- {fname} 不存在于仓库中，跳过")
    except Exception as e:
        print(f"- {fname} 下载失败: {e}，使用空文件")
        # 创建空文件
        fpath = os.path.join(output_dir, fname)
        if fname == "sent_records.json":
            with open(fpath, "w") as f:
                f.write("[]")
        elif fname == "company_detail_cache.json":
            with open(fpath, "w") as f:
                f.write("{}")
