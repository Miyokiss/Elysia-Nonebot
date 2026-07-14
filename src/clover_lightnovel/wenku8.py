import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
import requests
import src.configs.api_config as api_config
from src.utils.async_utils import run_sync

# 登录页面的URL
login_url = 'https://www.wenku8.net/login.php?jumpurl=http%3A%2F%2Fwww.wenku8.net%2Findex.php'
index_url = 'https://www.wenku8.net/index.php'

headers = {
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Connection': 'close',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.41'
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COOKIE_PATH = PROJECT_ROOT / "wenku8.cookie"
OUTPUT_PATH = Path(__file__).resolve().parent / "output1.html"


class ProxyProviderError(RuntimeError):
    """代理供应商返回了不可用或格式错误的代理。"""


def parse_proxy_host(payload: str) -> str:
    value = payload.strip()
    if not value:
        raise ProxyProviderError("代理服务返回空响应")

    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        candidate = value.splitlines()[0].strip()
    else:
        if not isinstance(data, dict):
            raise ProxyProviderError("代理服务返回格式错误")
        if data.get("success") is False or data.get("code") not in (None, 0, 200):
            raise ProxyProviderError(str(data.get("msg") or "代理套餐不可用"))
        raw_data = data.get("data")
        if isinstance(raw_data, str):
            candidate = raw_data.strip()
        elif isinstance(raw_data, list) and raw_data:
            first = raw_data[0]
            if isinstance(first, str):
                candidate = first.strip()
            elif isinstance(first, dict) and first.get("ip") and first.get("port"):
                candidate = f"{first['ip']}:{first['port']}"
            else:
                raise ProxyProviderError("代理服务未返回有效地址")
        else:
            raise ProxyProviderError("代理服务未返回有效地址")

    try:
        parsed = urlsplit(f"http://{candidate}")
        port = parsed.port
    except ValueError as exc:
        raise ProxyProviderError("代理地址端口无效") from exc
    if not parsed.hostname or port is None or parsed.path not in ("", "/"):
        raise ProxyProviderError("代理地址格式无效")
    return candidate

# 登录表单数据
login_data = {
    'username': api_config.wenku8_username,
    'password': api_config.wenku8_password,
    'usecookie': '0',
    'action': 'login'
}


def get_proxy(request_headers) -> dict[str, str] | None:
    proxy_enabled = getattr(api_config, "proxy_api_enabled", True)
    if not isinstance(proxy_enabled, bool):
        raise ProxyProviderError("proxy_api_enabled 必须配置为 True 或 False")
    if not proxy_enabled:
        return None

    # proxy_url可通过多米HTTP代理网站购买后生成代理api链接，每次请求api链接都是新的ip
    proxy_url = api_config.proxy_api
    if not proxy_url:
        raise ProxyProviderError("未配置代理服务地址")
    response = requests.get(proxy_url, headers=request_headers, timeout=10)
    response.raise_for_status()
    proxy_host = parse_proxy_host(response.text)
    # proxy_host='117.35.254.105:22001'
    # proxy_host='192.168.0.134:1080'
    proxy = {
        'http': 'http://' + proxy_host,
        'https': 'http://' + proxy_host
    }
    return proxy


def _login():
    # 发送登录请求
    with requests.Session() as session:
        proxy = get_proxy(headers)
        # 注意：这里使用了Session对象来保持会话状态
        login_response = session.post(
            login_url,
            data=login_data,
            headers=headers,
            proxies=proxy,
            timeout=20,
        )
        login_response.raise_for_status()

        # 检查登录是否成功（根据实际需求调整）
        if login_response.status_code == 200:
            # 登录成功后，Session对象已经自动保存了Cookie
            # 可以直接使用该Session对象访问受保护的页面
            # 获取 Cookie
            cookies = session.cookies

            # 保存 Cookie 到文件
            with COOKIE_PATH.open('w', encoding='utf-8') as f:
                for cookie in cookies:
                    f.write(f"{cookie.name}={cookie.value}; ")
        else:
            raise requests.HTTPError(f"登录失败，状态码：{login_response.status_code}")


async def login():
    await run_sync(_login)


def _get_books():
    from bs4 import BeautifulSoup

    with COOKIE_PATH.open('r', encoding='utf-8') as f:
        cookie = f.read()
    headers1 = {
        'Connection': 'close',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.41',
        'Cookie': cookie
    }
    proxy = get_proxy(headers1)
    response = requests.get(
        index_url, headers=headers1, proxies=proxy, timeout=20
    )
    response.raise_for_status()
    html = response.content.decode('gbk', errors='replace')
    soup = BeautifulSoup(html, 'html.parser')
    orders = soup.find_all(name='div', class_='block')
    head = """
    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
        "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta content="text/html; charset=utf-8" http-equiv="Content-Type"/>
    <title>轻小说文库 - 最新最全的日本动漫轻小说在线阅读与下载基地</title>
    <meta content="IE=EmulateIE7" http-equiv="X-UA-Compatible"/>
    <meta content="ie-comp" name="renderer"/>
    <meta content="轻小说,sf轻小说,dmzj轻小说,日本轻小说,动漫小说,轻小说电子书,轻小说TXT下载" name="keywords"/>
    <meta content="轻小说文库(www.wenku8.com)是收录最全更新最快的动漫sf轻小说网站,提供轻小说在线阅读,TXT与电子书下载,支持手机WAP访问."
          name="description"/>
    <meta content="no-cache" http-equiv="Cache-Control"/>
    <link href="style.css" media="all" rel="stylesheet" rev="stylesheet" type="text/css"/>
    <script language="javascript" src="/scripts/common.js" type="text/javascript"></script>
    <script language="javascript" src="/themes/wenku8/theme.js" type="text/javascript"></script>
<!--    <link rel="stylesheet" href="main.css">-->
</head>
    """
    # print(orders[7].text)
    if len(orders) < 11:
        raise ValueError(f"轻小说页面结构异常，仅找到 {len(orders)} 个内容区块")

    with OUTPUT_PATH.open('w', encoding='utf-8') as file:
        file.write(head + str(orders[7]).replace("2025年春季新番原作抢先看！(", "2025年春季新番原作抢先看！").replace(
            'target="_blank">查看 这本轻小说真厉害！2025 TOP榜单</a>)', '></a>') + str(orders[8]) + str(orders[9]) + str(
            orders[10]))


async def get_books():
    await run_sync(_get_books)


if __name__ == '__main__':
    asyncio.run(login())
    asyncio.run(get_books())
