import os
import time
import random
import re
import requests
import sys
import traceback
import json
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
    """验证破解器 (带有循环重试和截图调试)"""
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
                # 若不是第一次尝试，则先点击刷新按钮更换挑战
                if attempt > 0:
                    self.log("🔄 准备刷新验证码...")
                    reload_btn = iframe_ele.ele('css:#recaptcha-reload-button', timeout=3)
                    if reload_btn:
                        reload_btn.click()
                        self.log("🖱️ 点击了刷新重试")
                        time.sleep(random.uniform(3, 5))
                    else:
                        self.log("⚠️ 未找到刷新按钮，尝试直接继续...")

                src = self.get_audio_source(iframe_ele)
                
                if not src:
                    self.log("❌ 无法获取token链接 (风控拦截或音频被禁)")
                    try:
                        ss_name = f'recaptcha_no_audio_attempt_{attempt+1}_{int(time.time())}.png'
                        self.page.get_screenshot(path='.', name=ss_name)
                        self.log(f"📸 已保存获取音频失败截图: {ss_name}")
                    except: pass
                    continue # 尝试下一次循环

                self.log("📥 下载token...")
                mp3_file = "audio.mp3"
                wav_file = "audio.wav"
                
                # 清理之前的残留文件
                if os.path.exists(mp3_file): os.remove(mp3_file)
                if os.path.exists(wav_file): os.remove(wav_file)

                r = requests.get(src, timeout=15)
                if r.status_code != 200:
                    self.log(f"❌ 下载音频失败，状态码: {r.status_code}")
                    continue
                    
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
                    except Exception as e:
                        self.log(f"❌ 无法识别语音内容: {e}")
                        continue

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
                        self.log("🚀 提交验证...")
                        time.sleep(4)
                        
                        try:
                            if iframe_ele.states.is_displayed:
                                err = iframe_ele.ele('css:.rc-audiochallenge-error-message')
                                if err and err.states.is_displayed:
                                    self.log(f"❌ 验证未通过: {err.text}")
                                    # 未通过则进入下一次尝试 (可能要求多轮验证)
                                    continue
                        except:
                            pass # 元素消失或不可见，说明通过了
                        
                        self.log("✅ 验证通过")
                        try:
                            ss_name = f'recaptcha_success_{int(time.time())}.png'
                            self.page.get_screenshot(path='.', name=ss_name)
                            self.log(f"📸 已保存 reCAPTCHA 破解成功截图: {ss_name}")
                        except: pass
                        return True
                        
            except Exception as e:
                self.log(f"💥 单次尝试异常: {e}")
            finally:
                if os.path.exists("audio.mp3"): os.remove("audio.mp3")
                if os.path.exists("audio.wav"): os.remove("audio.wav")

        self.log("❌ 达到最大重试次数，破解彻底失败")
        try:
            ss_name = f'recaptcha_final_fail_{int(time.time())}.png'
            self.page.get_screenshot(path='.', name=ss_name)
            self.log(f"📸 已保存 reCAPTCHA 最终失败截图: {ss_name}")
        except: pass
        return False

    def get_audio_source(self, iframe_ele):
        try:
            err_msg = iframe_ele.ele('css:.rc-audiochallenge-error-message')
            if err_msg and err_msg.states.is_displayed:
                self.log(f"⛔ Google 拒绝: {err_msg.text}")
                return None
            
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
        self.email = os.getenv('WEB_EMAIL')
        self.password = os.getenv('WEB_PASSWORD')
        self.server_urls = [url.strip() for url in os.getenv('WEIRDHOST_SERVER_URLS', '').split(',') if url.strip()]
        self.tg_token = os.getenv('TG_BOT_TOKEN')
        self.tg_chat_id = os.getenv('TG_CHAT_ID')
        self.proxy_address = os.getenv('PROXY', '127.0.0.1:10808')
        
        self.cookie_json = os.getenv('WEIRDHOST_COOKIE', '[]')
        self.gh_token = os.getenv('GH_TOKEN')
        self.gh_repo = os.getenv('GITHUB_REPOSITORY') 
        self.secret_name = "WEIRDHOST_COOKIE"
        
        self.results = []

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        sys.stdout.flush()

    def send_tg_notification(self, message):
        if not self.tg_token or not self.tg_chat_id: return
        try:
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
                self.log(f"📅 解析到期日: {expiry} (剩余 {days} 天)")
                return days, expiry      
            return None, None
        except Exception as e: 
            self.log(f"⚠️ 时间解析出错: {str(e)[:50]}")
            return None, None

    def solve_turnstile(self, page, is_interstitial=False):
        mode_text = "[拦截页模式]" if is_interstitial else "[表单模式]"
        self.log(f"🛡️ 开始处理 Turnstile {mode_text}...")
        
        try:
            # --- 步骤 1: 检查是否已自动通过 (仅限表单模式) ---
            if not is_interstitial:
                try:
                    resp_input = page.ele('css:[name="cf-turnstile-response"]')
                    if resp_input and resp_input.value:
                        self.log("⚡ [自动通过] Token 已存在，无需点击！")
                        return True
                except:
                    pass

            # --- 步骤 2: 锁定 Iframe ---
            self.log("🔍 寻找 Turnstile iframe...")
            target_iframe = page.get_frame('css:iframe[src^="https://challenges.cloudflare.com"]', timeout=8)
            
            if not target_iframe:
                self.log("⚠️ 尝试通过 ID 前缀查找...")
                target_iframe = page.get_frame('css:iframe[id^="cf-chl-widget-"]', timeout=5)

            if not target_iframe:
                self.log("❌ 彻底找不到 iframe")
                page.get_screenshot(path='.', name='no_iframe.png')
                return False

            self.log("✅ 成功锁定 Iframe，准备穿透...")
            time.sleep(2) 

            # --- 步骤 3: 穿透 Closed Shadow Root ---
            click_success = False
            
            try:
                iframe_body = target_iframe.ele('tag:body')
                if not iframe_body:
                    raise Exception("无法获取 iframe body")

                sr = iframe_body.shadow_root
                
                if sr:
                    self.log("🔓 成功进入 Closed Shadow Root")
                    
                    target_ele = sr.ele('css:input[type="checkbox"]')
                    if not target_ele:
                        target_ele = sr.ele('css:div.main-wrapper') or sr.ele('css:#content')
                    
                    if target_ele:
                        self.log("🖱️ 在 ShadowRoot 内部找到目标，执行物理点击...")
                        target_ele.click.at(offset_x=10, offset_y=10)
                        click_success = True
                    else:
                        self.log("⚠️ ShadowRoot 内部未找到明显元素")
                else:
                    self.log("⚠️ 未检测到 ShadowRoot")

            except Exception as e:
                self.log(f"⚠️ 穿透点击尝试失败: {e}")

            # --- 步骤 4: (保底方案) 坐标盲点 ---
            if not click_success:
                self.log("🏹 [保底方案] 执行 Iframe 坐标盲点...")
                try:
                    target_iframe.frame_ele.click.at(offset_x=25, offset_y=30)
                    click_success = True
                except Exception as e:
                    self.log(f"❌ 盲点失败: {e}")

            # --- 步骤 5: 验证结果 ---
            if click_success:
                # 如果是拦截页，点完就走，不查 Token，交由外层检测 URL 跳转
                if is_interstitial:
                    self.log("⏳ [拦截页模式] 点击完成，跳过 Token 等待，交由主流程检测重定向...")
                    return True

                self.log("⏳ 点击已执行，等待验证通过...")
                for i in range(15):
                    time.sleep(1)
                    resp = page.ele('css:[name="cf-turnstile-response"]')
                    if resp and resp.value:
                        self.log(f"🎉 过盾成功！Token 已注入 (耗时 {i+1}s)")
                        return True
                    
                    if not page.ele('css:iframe[src^="https://challenges.cloudflare.com"]'):
                         resp = page.ele('css:[name="cf-turnstile-response"]')
                         if resp and resp.value:
                             self.log("🎉 过盾成功 (Iframe已消失)！")
                             return True
                
                self.log("⚠️ 等待超时，未获取到 Token")
                return False
            
            return False

        except Exception as e:
            self.log(f"🔥 Turnstile 处理异常: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def human_type(self, element, text):
        element.click()
        time.sleep(random.uniform(0.1, 0.3))
        element.clear()
        
        for char in text:
            element.input(char, clear=False)
            time.sleep(random.uniform(0.05, 0.2))
        
        time.sleep(random.uniform(0.3, 0.8))

    def human_move_and_click(self, page, element):
        try:
            page.actions.move_to(element, duration=random.uniform(0.5, 1.0))
            time.sleep(random.uniform(0.1, 0.3))
            element.click()
        except:
            element.click()

    def try_cookie_login(self, page):
        if not self.cookie_json or self.cookie_json.strip() == '[]' or self.cookie_json.strip() == '':
            return False
            
        self.log("🍪 发现缓存 Cookie，尝试使用 Cookie 登录...")
        try:
            cookies = json.loads(self.cookie_json)
            page.set.cookies(cookies)
            page.get("https://hub.weirdhost.xyz/auth/login")
            time.sleep(3)
            
            if "login" not in page.url:
                self.log("🎉 Cookie 登录成功！")
                return True
            else:
                self.log("⚠️ Cookie 登录失效或已过期，退回到账号密码登录...")
                try:
                    if hasattr(page, 'clear_cache'):
                        page.clear_cache(cookies=True)
                    elif hasattr(page, 'run_cdp'):
                        page.run_cdp('Network.clearBrowserCookies')
                    elif hasattr(page, '_run_cdp'):
                        page._run_cdp('Network.clearBrowserCookies')
                except Exception as clear_err:
                    self.log(f"⚠️ 清理旧 Cookie 失败: {clear_err}")
                return False
                
        except Exception as e:
            self.log(f"💥 Cookie 解析或注入异常: {e}")
            try:
                if hasattr(page, 'clear_cache'):
                    page.clear_cache(cookies=True)
                elif hasattr(page, '_run_cdp'):
                    page._run_cdp('Network.clearBrowserCookies')
            except:
                pass
            return False

    def do_login(self, page):
        self.log("🔑 执行账号密码登录 ...")
        
        try:
            self.log("⏳ 等待页面加载...")
            email_input = page.ele('css:input[name="username"]', timeout=15)
            
            if not email_input:
                self.log("❌ 页面加载超时或由于网络问题呈现白屏，找不到账号输入框。")
                try:
                    self.log("📸 尝试保存白屏现场截图...")
                    page.get_screenshot(path='.', name='login_blank_timeout.png')
                except Exception as ss_e:
                    self.log(f"⚠️ 截图失败，浏览器进程可能已假死: {ss_e}")
                return False

            self.log("✅ 页面加载完毕，准备输入...")
            
            try:
                page.scroll.to_bottom()
            except Exception as e:
                self.log(f"⚠️ 滚动页面失败 (可忽略): {e}")
            time.sleep(2)
            
            self.log("⌨️ 输入账号...")
            self.human_type(email_input, self.email)
            
            self.log("⌨️ 输入密码...")
            pass_input = page.ele('css:input[name="password"]')
            if pass_input:
                self.human_type(pass_input, self.password)
            else:
                self.log("❌ 找不到密码框")
                return False
            
            self.log("☑️ 勾选条款...")
            cb = page.ele('css:input[type="checkbox"]')
            if cb:
                if not cb.states.is_checked:
                    page.run_js('arguments[0].click()', cb)
                    time.sleep(0.5)
                if not cb.states.is_checked:
                    cb.click()

            time.sleep(1)
            
            self.log("🚀 提交登录...")
            pass_input.input('\n')
            
            self.log("👀 观察 (25s)...")
            login_btn = page.ele('css:button[type="submit"]') or page.ele('text:로그인')
            
            for i in range(25):
                if "login" not in page.url:
                    self.log(f"🎉 登录成功！(耗时 {i+1}s)")
                    return True

                challenge_frame = page.ele('css:iframe[src*="bframe"]')
                is_popup = False
                if challenge_frame:
                    try:
                        ele = challenge_frame.frame_ele if hasattr(challenge_frame, 'frame_ele') else challenge_frame
                        if ele.states.is_displayed:
                            is_popup = True
                    except: pass

                if is_popup:
                    self.log(f"🚨 第 {i+1} 秒检测到图片验证，启动破解...")
                    
                    solver = RecaptchaAudioSolver(page)
                    solver.set_logger(self.log)
                    
                    if solver.solve(challenge_frame):
                        self.log("🎉 验证通过！等待跳转...")
                        time.sleep(5)
                        if "login" not in page.url:
                            self.log("🎉 登录成功！")
                            return True
                    else:
                        self.log("❌ 破解失败")
                        return False 

                if i == 5 and login_btn and "login" in page.url:
                    self.log("⚠️ 回车似乎无响应，尝试 JS 强制点击按钮...")
                    page.run_js('arguments[0].click()', login_btn)
                
                err_p = page.ele('css:p.error') or page.ele('css:.input-help.error')
                if err_p and err_p.text:
                    self.log(f"🔴 检测到页面错误: {err_p.text}")
                    return False

                time.sleep(1)

            self.log("❌ 登录超时")
            try:
                self.log("📸 尝试保存超时页面截图...")
                page.get_screenshot(path='.', name='login_timeout.png')
            except Exception as ss_e:
                self.log(f"⚠️ 截图失败: {ss_e}")
            return False

        except Exception as e:
            self.log(f"💥 登录异常: {e}")
            traceback.print_exc()
            try:
                self.log("📸 尝试抓取崩溃页面截图...")
                page.get_screenshot(path='.', name='login_exception_crash.png')
            except Exception as ss_e:
                self.log(f"⚠️ 异常截图也失败了: {ss_e}")
            return False

    def check_and_update_cookies(self, page):
        self.log("🔍 检查核心 Cookie 是否需要更新...")
        try:
            current_cookies = page.cookies()
            if not current_cookies:
                return
            
            old_cookies = []
            if self.cookie_json and self.cookie_json.strip() not in ['', '[]']:
                try:
                    old_cookies = json.loads(self.cookie_json)
                except Exception:
                    pass
            
            old_remember_value = None
            for cookie in old_cookies:
                if cookie.get('name', '').startswith('remember_web_'):
                    old_remember_value = cookie.get('value')
                    break
            
            new_remember_value = None
            pure_cookie_list = []
            for cookie in current_cookies:
                if cookie.get('name', '').startswith('remember_web_'):
                    new_remember_value = cookie.get('value')
                    pure_cookie_list.append(cookie)
                    break
            
            if new_remember_value and new_remember_value != old_remember_value:
                self.log("🔄 检测到核心cookie (remember_web_*) 发生变化，准备保存至 GitHub Secret...")
                pure_cookie_str = json.dumps(pure_cookie_list)
                self.update_github_secret(self.secret_name, pure_cookie_str)
            elif not new_remember_value:
                self.log("⚠️ 未在当前浏览器中找到 remember_web_* cookie，放弃更新。")
            else:
                self.log("✅ 核心cookie (remember_web_*) 无变化，无需更新。")

        except Exception as e:
            self.log(f"💥 检查/更新 Cookie 异常: {e}")

    def update_github_secret(self, secret_name, secret_value):
        if not self.gh_token or not self.gh_repo:
            self.log("⚠️ 缺少 GH_TOKEN 或 GITHUB_REPOSITORY 环境变量，无法更新 Secret。")
            return
            
        if 'nacl' not in sys.modules:
            self.log("❌ 缺少 pynacl 库，无法加密 Secret。请在工作流中执行 pip install pynacl")
            return

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.gh_token}",
            "X-GitHub-Api-Version": "2022-11-28"
        }

        try:
            pub_key_url = f"https://api.github.com/repos/{self.gh_repo}/actions/secrets/public-key"
            r = requests.get(pub_key_url, headers=headers)
            if r.status_code != 200:
                self.log(f"❌ 获取仓库公钥失败: {r.text}")
                return
            key_data = r.json()
            key_id = key_data['key_id']
            key_value = key_data['key']

            public_key = nacl.public.PublicKey(key_value.encode('utf-8'), nacl.encoding.Base64Encoder())
            sealed_box = nacl.public.SealedBox(public_key)
            encrypted = sealed_box.encrypt(secret_value.encode('utf-8'))
            encrypted_value = b64encode(encrypted).decode('utf-8')

            update_url = f"https://api.github.com/repos/{self.gh_repo}/actions/secrets/{secret_name}"
            payload = {
                "encrypted_value": encrypted_value,
                "key_id": key_id
            }
            r_update = requests.put(update_url, headers=headers, json=payload)
            
            if r_update.status_code in [201, 204]:
                self.log(f"🎉 成功更新 GitHub Secret: {secret_name}")
            else:
                self.log(f"❌ GitHub Secret 更新失败: {r_update.text}")
                
        except Exception as e:
            self.log(f"💥 更新 GitHub Secret 发生系统异常: {e}")

    def run(self):
        self.log("🚀 启动自动化流程...")
        
        if not self.email or not self.password:
            self.log("❌ 致命错误: 未检测到 WEB_EMAIL 或 WEB_PASSWORD 环境变量！程序即将退出。")
            return

        co = ChromiumOptions()
        co.set_browser_path('/usr/bin/google-chrome')
        
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-setuid-sandbox') 
        co.set_argument('--disable-software-rasterizer')
        co.set_argument('--disable-extensions')
        co.set_argument('--disable-popup-blocking')
        co.set_argument('--ignore-certificate-errors')
        
        #补充防止弹出欢迎页面和默认浏览器检查的参数，防止浏览器启动卡死
        co.set_argument('--no-first-run')
        co.set_argument('--no-default-browser-check')
        
        co.set_argument('--window-size=1280,1024')
        co.headless(False)
        
        if self.proxy_address:
            if "://" in self.proxy_address:
                proxy_url = self.proxy_address
            else:
                proxy_url = f"socks5://{self.proxy_address}"
            
            co.set_argument(f'--proxy-server={proxy_url}')
            self.log(f"🌐 代理已配置: {proxy_url}")
        
        import tempfile, shutil
        user_data_dir = tempfile.mkdtemp()
        co.set_user_data_path(user_data_dir)
        co.auto_port()
        
        page = None
        try:
            page = ChromiumPage(co)
            self.log("🔗 打开登录页...")
            page.get("https://hub.weirdhost.xyz/auth/login", retry=3)

            # ---------------------------------------------------------
            # 优化: 登录前的 Turnstile 安全验证处理逻辑 (含截图调试)
            # ---------------------------------------------------------
            max_retries = 3
            for attempt in range(max_retries):
                time.sleep(3) # 等待页面加载
                
                # 检查是否直接看到账号输入框，设置 timeout=2 避免阻塞
                if page.ele('css:input[name="username"]', timeout=2):
                    self.log("✅ 已成功进入正式登录界面，无需额外验证")
                    break
                    
                # 检查 CF Turnstile iframe，设置 timeout=2
                if page.ele('css:iframe[src^="https://challenges.cloudflare.com"]', timeout=2) or page.ele('css:iframe[id^="cf-chl-widget-"]', timeout=2):
                    self.log(f"🚧 发现登录前的 Turnstile 安全验证 (第 {attempt + 1}/{max_retries} 次尝试)...")
                    
                    # 传入 is_interstitial=True，不再死等 Token
                    self.solve_turnstile(page, is_interstitial=True)
                    self.log("⏳ 等待页面验证通过后自动跳转 (最多等待 30s)...")
                    
                    success_bypass = False
                    # 循环检测账号输入框的出现
                    for i in range(30):
                        # 极短超时 (timeout=0.5s)，总耗时 = 30 * (0.5s timeout + 0.5s sleep) = 约 30 秒
                        if page.ele('css:input[name="username"]', timeout=0.5):
                            self.log("✅ 成功重定向进入正式登录界面")
                            try:
                                ss_name = f'interstitial_success_{int(time.time())}.png'
                                page.get_screenshot(path='.', name=ss_name)
                                self.log(f"📸 首页盾通过，保存截图: {ss_name}")
                            except: pass
                            success_bypass = True
                            break
                        time.sleep(0.5)
                        
                    if success_bypass:
                        break
                    else:
                        self.log(f"⚠️ 第 {attempt + 1} 次尝试未能进入登录页。")
                        try:
                            ss_name = f'interstitial_fail_attempt_{attempt+1}_{int(time.time())}.png'
                            page.get_screenshot(path='.', name=ss_name)
                            self.log(f"📸 首页盾未通过，保存截图: {ss_name}")
                        except: pass
                        
                        if attempt < max_retries - 1:
                            self.log("🔄 准备刷新页面重试...")
                            page.refresh()
                            time.sleep(3)
                        else:
                            self.log("❌ 达到最大重试次数，放弃当前验证流程。")
                else:
                    self.log("⚠️ 页面既没有输入框也没有找到验证码 iframe，可能还在加载中...")
                    time.sleep(2)
            # ---------------------------------------------------------

            login_success = False
            if self.try_cookie_login(page):
                login_success = True
            else:
                if self.do_login(page):
                    login_success = True

            if login_success:
                self.log("✅ 登录成功，开始处理续期...")
                for url in self.server_urls:
                    srv_id = url.split('/')[-1]
                    self.log(f"\n⚡ 服务器: {srv_id}")
                    page.get(url)
                    page.wait.load_start()
                    time.sleep(5)
                    
                    if "login" in page.url or "시간" not in page.html:
                        if not re.search(r'202\d-\d{2}-\d{2}', page.html):
                            self.log("❌ 无法进入后台 (Cookie 可能失效)")
                            self.results.append(f"状态: ❌ Cookie 失效/登录失败")
                            continue

                    self.log("✅ 已进入管理面板")
                    
                    days, expiry = self.get_remaining_days(page)
                    expiry_txt = f"📅 到期: {expiry.strftime('%Y-%m-%d') if expiry else '?'}\n"
                    
                    if days is not None and days > 7:
                        self.log(f"⏭️ 剩余 {days} 天，跳过")
                        self.results.append(f"✅ {srv_id}: 无需续期")
                        continue
                    
                    self.log("🔄 续期中...")
                    renew_btn = page.ele('css:button.bkrtgq') or page.ele('text:Extend') or page.ele('text:연장하기') or page.ele('text:연장 하기')
                    
                    status = "未知状态"
                    
                    if renew_btn:
                        try:
                            renew_btn.click()
                            self.log("🖱️ 点击了续期按钮")
                            time.sleep(5)

                            passed_captcha = True
                            if page.ele('css:[name="cf-turnstile-response"]'):
                                self.log("🚧 检测到 Turnstile 验证")
                                if self.solve_turnstile(page):
                                    time.sleep(3)
                                    if page.ele('css:button.bkrtgq'):
                                        page.ele('css:button.bkrtgq').click()
                                else:
                                    passed_captcha = False
                                    status = "❌ <b>Turnstile 验证失败</b>"
                            else:
                                self.log("⚡ 未触发验证，直接通过")

                            if passed_captcha:
                                self.log("⏳ 正在等待过盾后的弹窗...")
                                
                                next_btn = None
                                for _ in range(10):
                                    next_btn = (
                                        page.ele('css:div[class*="Popup__Styled"] button') or
                                        page.ele('xpath://button[contains(., "Next") or contains(., "NEXT")]')
                                    )
                                    if next_btn:
                                        break
                                    time.sleep(1)

                                if next_btn:
                                    self.log("✅ 成功捕捉到弹窗及底部按钮！")
                                    
                                    body_text = page.ele('tag:body').text
                                    
                                    if '성공' in body_text or 'SUCCESS' in body_text.upper() or '연장' in body_text:
                                        self.log("✅ 全局扫描识别到成功特征词 (성공/연장)")
                                        status = "🎉 <b>续期成功 (弹窗确认)</b>"
                                    elif '아직' in body_text or 'ERROR' in body_text.upper() or '없어요' in body_text:
                                        self.log("⚠️ 全局扫描识别到冷却期特征词 (아직/없어요)")
                                        status = "⏳ <b>冷却中 (时间未到)</b>"
                                    else:
                                        self.log("❓ 弹窗已出现，但未能匹配到明确的状态文字")
                                        status = "✅ <b>操作完成 (状态未知)</b>"
                                    
                                    self.log("🖱️ 点击弹窗按钮 (NEXT)...")
                                    try:
                                        next_btn.click()
                                    except:
                                        page.run_js('arguments[0].click()', next_btn)
                                    
                                    self.log("⏳ 等待确认弹窗出现...")
                                    time.sleep(2)
                                    
                                    close_btn = None
                                    for _ in range(5):
                                        close_btn = (
                                            page.ele('css:div[class*="Popup__Styled"] button') or
                                            page.ele('xpath://button[contains(., "닫기")]')
                                        )
                                        if close_btn:
                                            break
                                        time.sleep(1)
                                        
                                    if close_btn:
                                        self.log("🖱️ 找到关闭按钮，点击...")
                                        try:
                                            close_btn.click()
                                        except:
                                            page.run_js('arguments[0].click()', close_btn)
                                        time.sleep(1)
                                    else:
                                        self.log("⚠️ 未检测到关闭按钮，可能已经自动消失。")

                                else:
                                    self.log("⚠️ 10秒内未检测到弹窗...")
                                    
                                    try:
                                        screenshot_name = f'no_popup_{srv_id}_{int(time.time())}.png'
                                        self.log(f"📸 正在保存现场截图至: {screenshot_name}")
                                        page.get_screenshot(path='.', name=screenshot_name)
                                    except Exception as ss_e:
                                        self.log(f"⚠️ 现场截图失败: {ss_e}")
                                    
                                    body_text = page.ele('tag:body').text
                                    if 'SUCCESS' in body_text.upper() or '성공' in body_text:
                                        status = "🎉 <b>续期成功 (文本确认)</b>"
                                    elif 'ERROR' in body_text.upper() or '아직' in body_text:
                                        status = "⏳ <b>冷却中 (文本确认)</b>"
                                    else:
                                        status = "🎉 <b>续期已提交 (无明显提示)</b>"

                        except Exception as e:
                            self.log(f"⚠️ 点击续期按钮异常: {e}")
                            status = "❌ <b>点击异常</b>"
                    else:
                        self.log("⚠️ 未找到续期按钮")
                        status = "❓ <b>未找到按钮</b>"

                    try:
                        final_screenshot_name = f'final_state_{srv_id}_{int(time.time())}.png'
                        self.log(f"📸 正在保存最终确认截图至: {final_screenshot_name}")
                        page.get_screenshot(path='.', name=final_screenshot_name)
                    except Exception as ss_e:
                        self.log(f"⚠️ 最终截图失败: {ss_e}")
                    
                    page.refresh()
                    time.sleep(5)
                    new_days, new_date = self.get_remaining_days(page)
                    if new_days is not None and new_date:
                        expiry_txt = f"📅 新到期: {new_date.strftime('%Y-%m-%d')}\n"
                    
                    self.results.append(f"{expiry_txt}状态: {status}")

        except Exception as e:
            self.log(f"💥 脚本崩溃: {e}")
            traceback.print_exc()
        finally:
            if self.results:
                msg = "<b>🤖 Weirdhost 续期报告</b>\n" + "\n".join(self.results)
                self.send_tg_notification(msg)
            
            if page: 
                self.check_and_update_cookies(page)
                page.quit()
                
            try: shutil.rmtree(user_data_dir, ignore_errors=True)
            except: pass

if __name__ == "__main__":
    bot = WeirdhostGHA()
    bot.run()
