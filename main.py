import os
import time
import random
import re
import requests
import sys
import traceback
import json
import shutil
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

try:
    import nacl.public
    import nacl.encoding
    from base64 import b64encode
except ImportError:
    pass

class WeirdhostGHA:
    def __init__(self):
        self.tg_token = os.getenv('TG_BOT_TOKEN')
        self.tg_chat_id = os.getenv('TG_CHAT_ID')
        self.proxy_address = os.getenv('PROXY', '127.0.0.1:10808')
        self.gh_token = os.getenv('GH_TOKEN')
        self.gh_repo = os.getenv('GITHUB_REPOSITORY') 
        
        self.accounts = []
        for i in range(1, 11):
            cookie_val = os.getenv(f'WEIRDHOST_COOKIE_{i}')
            urls_val = os.getenv(f'WEIRDHOST_SERVER_URLS_{i}')
            if cookie_val and urls_val:
                self.accounts.append({
                    'index': i,
                    'secret_name': f'WEIRDHOST_COOKIE_{i}',
                    'cookie': cookie_val.strip(),
                    'urls': [u.strip() for u in urls_val.split(',') if u.strip()]
                })

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        sys.stdout.flush()

    def send_tg_notification(self, message, photo_path=None):
        if not self.tg_token or not self.tg_chat_id: return
        try:
            if photo_path and os.path.exists(photo_path):
                url = f"https://api.telegram.org/bot{self.tg_token}/sendPhoto"
                with open(photo_path, 'rb') as photo:
                    payload = {"chat_id": self.tg_chat_id, "caption": message, "parse_mode": "HTML"}
                    requests.post(url, data=payload, files={"photo": photo}, timeout=20)
            else:
                url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
                payload = {"chat_id": self.tg_chat_id, "text": message, "parse_mode": "HTML"}
                requests.post(url, json=payload, timeout=10)
            self.log("📤 TG 通知已发送")
        except Exception as e:
            self.log(f"❌ TG 发送失败: {e}")

    def get_remaining_days(self, page):
        try:
            match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', page.html)
            if match:
                expiry = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                days = (expiry - datetime.now()).days
                return days, expiry      
            return None, None
        except: return None, None

    def solve_turnstile(self, page, is_interstitial=False):
        mode_text = "[拦截页模式]" if is_interstitial else "[表单模式]"
        self.log(f"🛡️ 开始处理 Turnstile {mode_text}...")
        try:
            if not is_interstitial:
                try:
                    resp_input = page.ele('css:[name="cf-turnstile-response"]')
                    if resp_input and resp_input.value: return True
                except: pass

            target_iframe = page.get_frame('css:iframe[src^="https://challenges.cloudflare.com"]', timeout=8) or \
                            page.get_frame('css:iframe[id^="cf-chl-widget-"]', timeout=5)

            if not target_iframe: return False
            time.sleep(2) 

            click_success = False
            try:
                iframe_body = target_iframe.ele('tag:body')
                if iframe_body and iframe_body.shadow_root:
                    target_ele = iframe_body.shadow_root.ele('css:input[type="checkbox"]') or \
                                 iframe_body.shadow_root.ele('css:div.main-wrapper')
                    if target_ele:
                        target_ele.click.at(offset_x=10, offset_y=10)
                        click_success = True
            except: pass

            if not click_success:
                try:
                    target_iframe.frame_ele.click.at(offset_x=25, offset_y=30)
                    click_success = True
                except: pass

            if click_success:
                if is_interstitial: 
                    self.log("⏳ [拦截页模式] 点击完成，交由主流程检测重定向...")
                    return True
                for _ in range(15):
                    time.sleep(1)
                    resp = page.ele('css:[name="cf-turnstile-response"]')
                    if resp and resp.value: return True
            return False
        except: return False
            
    def try_cookie_login(self, page, cookie_json):
        self.log("🍪 尝试使用 Cookie 免密登录...")
        try:
            # 关键修复：必须先访问目标域名建立上下文，再设置 Cookie
            page.get("https://hub.weirdhost.xyz/auth/login", retry=3)
            time.sleep(3)
            
            # 处理可能的首页盾
            if page.ele('css:iframe[src^="https://challenges.cloudflare.com"]', timeout=2):
                self.log("🚧 发现登录前的 Turnstile 安全验证...")
                self.solve_turnstile(page, is_interstitial=True)
                self.log("⏳ 等待页面验证通过后自动跳转 (最多等待 30s)...")
                for _ in range(30):
                    if "login" in page.url or page.ele('css:input[name="username"]', timeout=0.5): break
                    time.sleep(0.5)
            
            # 此时页面必定是在 /auth/login 或者已经带有效域名的状态下
            cookies = json.loads(cookie_json)
            page.set.cookies(cookies)
            
            # 重新加载页面让 Cookie 生效
            self.log("🔄 注入 Cookie 后重新加载页面...")
            page.get("https://hub.weirdhost.xyz/auth/login")
            time.sleep(3)
            
            if "login" not in page.url:
                self.log("🎉 Cookie 登录成功！")
                return True
            else:
                self.log("❌ Cookie 已失效！无法进入后台，请重新抓取 Cookie！")
                return False
        except Exception as e:
            self.log(f"💥 Cookie 解析异常: {e}")
            return False

    def check_and_update_cookies(self, page, secret_name, old_cookie_json):
        self.log(f"🔍 检查账号 {secret_name} 的 Cookie 是否需要更新...")
        try:
            current_cookies = page.cookies()
            if not current_cookies: return
            
            old_remember_value = None
            if old_cookie_json and old_cookie_json.strip() not in ['', '[]']:
                try:
                    old_cookies = json.loads(old_cookie_json)
                    for c in old_cookies:
                        if c.get('name', '').startswith('remember_web_'):
                            old_remember_value = c.get('value')
                            break
                except: pass
            
            new_remember_value = None
            pure_cookie_list = []
            for cookie in current_cookies:
                if cookie.get('name', '').startswith('remember_web_'):
                    new_remember_value = cookie.get('value')
                    pure_cookie_list.append(cookie)
                    break
            
            if new_remember_value and new_remember_value != old_remember_value:
                self.log("🔄 检测到核心 Cookie 变化，自动更新 GitHub Secret...")
                self.update_github_secret(secret_name, json.dumps(pure_cookie_list))
            else:
                self.log("✅ 核心 Cookie 无变化。")
        except Exception as e:
            self.log(f"💥 检查/更新 Cookie 异常: {e}")

    def update_github_secret(self, secret_name, secret_value):
        if not self.gh_token or not self.gh_repo: return
        if 'nacl' not in sys.modules: return

        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.gh_token}", "X-GitHub-Api-Version": "2022-11-28"}
        try:
            r = requests.get(f"https://api.github.com/repos/{self.gh_repo}/actions/secrets/public-key", headers=headers)
            if r.status_code != 200: return
            key_data = r.json()

            public_key = nacl.public.PublicKey(key_data['key'].encode('utf-8'), nacl.encoding.Base64Encoder())
            encrypted = b64encode(nacl.public.SealedBox(public_key).encrypt(secret_value.encode('utf-8'))).decode('utf-8')

            r_update = requests.put(f"https://api.github.com/repos/{self.gh_repo}/actions/secrets/{secret_name}", headers=headers, json={"encrypted_value": encrypted, "key_id": key_data['key_id']})
            if r_update.status_code in [201, 204]: self.log(f"🎉 成功更新 Secret: {secret_name}")
        except Exception as e:
            self.log(f"💥 Secret 更新异常: {e}")

    def run(self):
        self.log("🚀 启动自动化流程 (多账号 Cookie 免密严格注入版)...")
        if not self.accounts:
            self.log("❌ 未检测到任何 WEIRDHOST_COOKIE_X 配置，退出。")
            return

        co = ChromiumOptions()
        co.set_browser_path('/usr/bin/google-chrome')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--no-first-run')
        co.set_argument('--no-default-browser-check')
        co.set_argument('--window-size=1280,1024')
        co.headless(False)
        
        if self.proxy_address:
            proxy_url = self.proxy_address if "://" in self.proxy_address else f"socks5://{self.proxy_address}"
            co.set_argument(f'--proxy-server={proxy_url}')
            self.log(f"🌐 代理已配置: {proxy_url}")
        
        import tempfile
        user_data_dir = tempfile.mkdtemp()
        co.set_user_data_path(user_data_dir)
        co.auto_port()
        
        page = None
        try:
            page = ChromiumPage(co)
            
            for acc in self.accounts:
                self.log(f"\n{'='*50}\n🚀 开始处理账号 [{acc['index']}]\n{'='*50}")
                
                try: page.clear_cache(cookies=True)
                except: pass

                if not self.try_cookie_login(page, acc['cookie']):
                    try:
                        ss_name = f'cookie_fail_acc{acc["index"]}.png'
                        page.get_screenshot(path='.', name=ss_name)
                    except: ss_name = None
                    msg = f"🤖 <b>Weirdhost 续期报告</b> 🐾\n👤 账号: {acc['index']}\n❌ <b>状态: Cookie 已失效！</b>\n⚠️ <i>请重新抓取并更新 WEIRDHOST_COOKIE_{acc['index']}</i>"
                    self.send_tg_notification(msg, ss_name)
                    continue

                for url in acc['urls']:
                    srv_id = url.split('/')[-1]
                    self.log(f"\n⚡ 正在潜入服务器: {srv_id}")
                    page.get(url)
                    page.wait.load_start()
                    time.sleep(5)
                    
                    if "login" in page.url or "시간" not in page.html:
                        if not re.search(r'202\d-\d{2}-\d{2}', page.html):
                            self.log("❌ 无法进入后台 (被阻断)")
                            continue

                    self.log("✅ 已进入管理面板")
                    days, expiry = self.get_remaining_days(page)
                    expiry_str = expiry.strftime('%Y-%m-%d %H:%M:%S') if expiry else '未知'
                    
                    if days is not None and days > 7:
                        self.log(f"⏭️ 剩余 {days} 天，跳过")
                        ss_name = f'status_skip_{srv_id}_{int(time.time())}.png'
                        page.get_screenshot(path='.', name=ss_name)
                        
                        msg = f"🤖 <b>Weirdhost 续期报告</b> 🐾\n👤 账号: {acc['index']}\n✅ <code>{srv_id}</code>: 无需续期\n📅 解析到期日: {expiry_str} (剩余 {days} 天)\n⏭️ 剩余 {days} 天，跳过"
                        self.send_tg_notification(msg, ss_name)
                        continue
                    
                    self.log("🔄 满足条件，尝试续期...")
                    renew_btn = page.ele('css:button.bkrtgq') or page.ele('text:Extend') or page.ele('text:연장하기') or page.ele('text:연장 하기')
                    status = "未知"
                    
                    if renew_btn:
                        try:
                            renew_btn.click()
                            time.sleep(5)

                            if page.ele('css:[name="cf-turnstile-response"]'):
                                if self.solve_turnstile(page):
                                    time.sleep(3)
                                    if page.ele('css:button.bkrtgq'): page.ele('css:button.bkrtgq').click()
                                else: status = "❌ Turnstile 验证失败"
                            
                            self.log("⏳ 等待弹窗...")
                            next_btn = None
                            for _ in range(10):
                                next_btn = page.ele('css:div[class*="Popup__Styled"] button') or page.ele('xpath://button[contains(., "Next") or contains(., "NEXT")]')
                                if next_btn: break
                                time.sleep(1)

                            if next_btn:
                                body_text = page.ele('tag:body').text
                                if '성공' in body_text or 'SUCCESS' in body_text.upper() or '연장' in body_text: status = "🎉 续期成功"
                                elif '아직' in body_text or 'ERROR' in body_text.upper() or '없어요' in body_text: status = "⏳ 冷却中"
                                else: status = "✅ 已点击 (状态未知)"
                                
                                try: next_btn.click()
                                except: page.run_js('arguments[0].click()', next_btn)
                            else:
                                body_text = page.ele('tag:body').text
                                if 'SUCCESS' in body_text.upper() or '성공' in body_text: status = "🎉 续期成功"
                                elif 'ERROR' in body_text.upper() or '아직' in body_text: status = "⏳ 冷却中"
                                else: status = "🎉 已提交"

                        except Exception as e:
                            self.log(f"⚠️ 点击续期按钮异常: {e}")
                            status = "❌ 点击异常"
                    else:
                        status = "❓ 未找到续期按钮"

                    page.refresh()
                    time.sleep(5)
                    
                    final_ss = f'final_{srv_id}_{int(time.time())}.png'
                    page.get_screenshot(path='.', name=final_ss)
                    
                    new_days, new_date = self.get_remaining_days(page)
                    new_date_str = new_date.strftime('%Y-%m-%d %H:%M:%S') if new_date else '未知'
                    
                    msg = f"🤖 <b>Weirdhost 续期报告</b> 🐾\n👤 账号: {acc['index']}\n🔄 <code>{srv_id}</code>: {status}\n📅 解析到期日: {new_date_str}"
                    if new_days is not None: msg += f" (剩余 {new_days} 天)"
                    
                    self.send_tg_notification(msg, final_ss)

                self.check_and_update_cookies(page, acc['secret_name'], acc['cookie'])

        except Exception as e:
            self.log(f"💥 脚本崩溃: {e}")
            traceback.print_exc()
        finally:
            if page: page.quit()
            try: shutil.rmtree(user_data_dir, ignore_errors=True)
            except: pass

if __name__ == "__main__":
    bot = WeirdhostGHA()
    bot.run()
