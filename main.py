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

try:
    import speech_recognition as sr
    from pydub import AudioSegment
except ImportError:
    pass

class RecaptchaAudioSolver:
    """验证破解器"""
    def __init__(self, page):
        self.page = page
        self.log_func = print
        self.max_retries = 3

    def set_logger(self, func):
        self.log_func = func

    def log(self, msg):
        self.log_func(f"[Solver] {msg}")

    def solve(self, iframe_ele):
        self.log("🎧 启动破解流程...")
        try:
            audio_btn = iframe_ele.ele('css:#recaptcha-audio-button', timeout=3)
            if not audio_btn:
                self.log("❌ 未找到破解按钮")
                return False
            audio_btn.click()
            self.log("🖱️ 点击了破解按钮")
            time.sleep(random.uniform(2, 4)) 
        except Exception as e:
            self.log(f"❌ 初始点击音频按钮失败: {e}")
            return False

        for attempt in range(self.max_retries):
            self.log(f"🔄 开始第 {attempt + 1}/{self.max_retries} 次破解尝试...")
            try:
                if attempt > 0:
                    reload_btn = iframe_ele.ele('css:#recaptcha-reload-button', timeout=3)
                    if reload_btn:
                        reload_btn.click()
                        time.sleep(random.uniform(3, 5))

                src = self.get_audio_source(iframe_ele)
                if not src:
                    self.log("❌ 无法获取token链接")
                    continue 

                self.log("📥 下载token...")
                mp3_file = "audio.mp3"
                wav_file = "audio.wav"
                
                if os.path.exists(mp3_file): os.remove(mp3_file)
                if os.path.exists(wav_file): os.remove(wav_file)

                r = requests.get(src, timeout=15)
                if r.status_code != 200: continue
                    
                with open(mp3_file, 'wb') as f: f.write(r.content)
                
                try:
                    sound = AudioSegment.from_mp3(mp3_file)
                    sound.export(wav_file, format="wav")
                except Exception as e:
                    self.log(f"❌ ffmpeg 转码失败: {e}")
                    continue

                key_text = ""
                recognizer = sr.Recognizer()
                with sr.AudioFile(wav_file) as source:
                    audio_data = recognizer.record(source)
                    try:
                        key_text = recognizer.recognize_google(audio_data)
                        self.log(f"🗣️ 识别结果: [{key_text}]")
                    except: continue

                input_box = iframe_ele.ele('css:#audio-response')
                if input_box:
                    input_box.click()
                    time.sleep(0.5)
                    for char in key_text:
                        input_box.input(char, clear=False)
                        time.sleep(random.uniform(0.05, 0.15))
                    
                    time.sleep(1)
                    verify_btn = iframe_ele.ele('css:#recaptcha-verify-button')
                    if verify_btn:
                        verify_btn.click()
                        time.sleep(4)
                        
                        try:
                            if iframe_ele.states.is_displayed:
                                err = iframe_ele.ele('css:.rc-audiochallenge-error-message')
                                if err and err.states.is_displayed:
                                    self.log(f"❌ 验证未通过: {err.text}")
                                    continue
                        except: pass
                        
                        self.log("✅ 验证通过")
                        return True
                        
            except Exception as e:
                self.log(f"💥 单次尝试异常: {e}")
            finally:
                if os.path.exists("audio.mp3"): os.remove("audio.mp3")
                if os.path.exists("audio.wav"): os.remove("audio.wav")

        self.log("❌ 破解彻底失败")
        return False

    def get_audio_source(self, iframe_ele):
        try:
            download_link = iframe_ele.ele('css:.rc-audiochallenge-ndownload-link') or \
                            iframe_ele.ele('css:a.rc-audiochallenge-download-link') or \
                            iframe_ele.ele('xpath://a[contains(@href, ".mp3")]')
            if download_link: return download_link.attr('href')
            
            audio_tag = iframe_ele.ele('css:#audio-source')
            if audio_tag: return audio_tag.attr('src')
            return None
        except: return None

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
            page.get("https://hub.weirdhost.xyz/auth/login", retry=3)
            time.sleep(3)
            
            if page.ele('css:iframe[src^="https://challenges.cloudflare.com"]', timeout=2):
                self.log("🚧 发现登录前的 Turnstile 安全验证...")
                self.solve_turnstile(page, is_interstitial=True)
                self.log("⏳ 等待页面验证通过后自动跳转 (最多等待 30s)...")
                for _ in range(30):
                    if "login" in page.url or page.ele('css:input[name="username"]', timeout=0.5): break
                    time.sleep(0.5)
            
            cookies = json.loads(cookie_json)
            page.set.cookies(cookies)
            
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
        except: pass

    def run(self):
        self.log("🚀 启动极速自动化流程 (修复性能 Bug 版)...")
        if not self.accounts:
            self.log("❌ 致命错误: 未检测到任何 WEIRDHOST_COOKIE 配置！")
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
                    msg = f"🤖 <b>Weirdhost 续期报告</b> 🐾\n👤 账号: {acc['index']}\n❌ <b>状态: Cookie 已失效/解析失败！</b>\n⚠️ <i>请重新抓取 Cookie 并更新</i>"
                    self.send_tg_notification(msg, ss_name)
                    continue

                for url in acc['urls']:
                    srv_id = url.split('/')[-1]
                    self.log(f"\n⚡ 服务器: {srv_id}")
                    page.get(url)
                    page.wait.load_start()
                    time.sleep(5)
                    
                    if "login" in page.url or "시간" not in page.html:
                        if not re.search(r'202\d-\d{2}-\d{2}', page.html):
                            self.log("❌ 无法进入后台 (被阻断)")
                            continue

                    self.log("✅ 已进入管理面板")
                    days, expiry = self.get_remaining_days(page)
                    expiry_str = expiry.strftime('%Y-%m-%d %H:%M:%S') if expiry else '未知时间'
                    
                    if days is not None and days > 7:
                        self.log(f"📅 解析到期日: {expiry_str} (剩余 {days} 天)")
                        self.log(f"⏭️ 剩余 {days} 天，跳过")
                        ss_name = f'status_skip_{srv_id}.png'
                        page.get_screenshot(path='.', name=ss_name)
                        
                        msg = f"🤖 <b>Weirdhost 续期报告</b>\n✅ {srv_id}: 无需续期\n📅 解析到期日: {expiry_str} (剩余 {days} 天)\n⏭️ 剩余 {days} 天，跳过"
                        self.send_tg_notification(msg, ss_name)
                        continue
                    
                    self.log("🔄 续期中...")
                    
                    # ⚠️ 性能修复 1：加上极其重要的 timeout=1
                    renew_btn = (page.ele('css:button.bkrtgq', timeout=1) or 
                                 page.ele('text:Extend', timeout=1) or 
                                 page.ele('text:연장하기', timeout=1) or 
                                 page.ele('text:연장 하기', timeout=1))
                                 
                    status = "未知状态"
                    
                    if renew_btn:
                        try:
                            renew_btn.click()
                            self.log("🖱️ 点击了续期按钮")
                            time.sleep(5)

                            passed_captcha = True
                            if page.ele('css:[name="cf-turnstile-response"]', timeout=2):
                                self.log("🚧 检测到 Turnstile 验证")
                                if self.solve_turnstile(page):
                                    time.sleep(3)
                                    if page.ele('css:button.bkrtgq', timeout=1): 
                                        page.ele('css:button.bkrtgq', timeout=1).click()
                                else:
                                    passed_captcha = False
                                    status = "❌ Turnstile 验证失败"
                            else:
                                self.log("⚡ 未触发验证，直接通过")

                            if passed_captcha:
                                self.log("⏳ 正在极速探测过盾后的弹窗...")
                                next_btn = None
                                for _ in range(10):
                                    # ⚠️ 性能修复 2：加上极其重要的 timeout=0.5
                                    next_btn = (page.ele('css:div[class*="Popup__Styled"] button', timeout=0.5) or 
                                                page.ele('xpath://button[contains(., "Next") or contains(., "NEXT")]', timeout=0.5))
                                    if next_btn: break
                                    time.sleep(1)

                                if next_btn:
                                    body_text = page.ele('tag:body').text
                                    if '성공' in body_text or 'SUCCESS' in body_text.upper() or '연장' in body_text:
                                        status = "🎉 续期成功"
                                    elif '아직' in body_text or 'ERROR' in body_text.upper() or '없어요' in body_text:
                                        status = "⏳ 冷却中"
                                    else:
                                        status = "✅ 操作完成 (状态未知)"
                                        
                                    self.log(f"📌 状态判定: {status}")
                                    try: next_btn.click()
                                    except: page.run_js('arguments[0].click()', next_btn)
                                    
                                    time.sleep(2)
                                    close_btn = None
                                    for _ in range(5):
                                        # ⚠️ 性能修复 3：加上极其重要的 timeout=0.5
                                        close_btn = (page.ele('css:div[class*="Popup__Styled"] button', timeout=0.5) or 
                                                     page.ele('xpath://button[contains(., "닫기")]', timeout=0.5))
                                        if close_btn: break
                                        time.sleep(1)
                                        
                                    if close_btn:
                                        try: close_btn.click()
                                        except: page.run_js('arguments[0].click()', close_btn)
                                        time.sleep(1)
                                else:
                                    body_text = page.ele('tag:body').text
                                    if 'SUCCESS' in body_text.upper() or '성공' in body_text: status = "🎉 续期成功"
                                    elif 'ERROR' in body_text.upper() or '아직' in body_text: status = "⏳ 冷却中"
                                    else: status = "🎉 续期已提交"
                                    self.log(f"📌 状态判定 (无弹窗): {status}")

                        except Exception as e:
                            self.log(f"⚠️ 点击续期按钮异常: {e}")
                            status = "❌ 点击异常"
                    else:
                        self.log("⚠️ 未找到续期按钮")
                        status = "❓ 未找到按钮"
                    
                    page.refresh()
                    time.sleep(5)
                    
                    final_ss = f'final_state_{srv_id}.png'
                    page.get_screenshot(path='.', name=final_ss)
                    
                    new_days, new_date = self.get_remaining_days(page)
                    new_date_str = new_date.strftime('%Y-%m-%d %H:%M:%S') if new_date else '未知时间'
                    
                    msg = f"🤖 <b>Weirdhost 续期报告</b>\n"
                    if status == "🎉 续期成功" or status == "🎉 续期已提交":
                        msg += f"✅ {srv_id}: 续期成功\n📅 解析到期日: {new_date_str}"
                        if new_days is not None: msg += f" (剩余 {new_days} 天)"
                    else:
                        msg += f"🔄 {srv_id}: {status}\n📅 当前到期日: {new_date_str}"
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
