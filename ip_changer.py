import asyncio
import requests
import time
import json
import random
import uuid
from playwright.async_api import async_playwright

# Proxy configuration
PROXIES = [
    {
        "username": "39634c565017cb0f383f",
        "password": "67b4c29c5a44697c",
        "host": "gw.dataimpulse.com",
        "port": 823
    }
]

PASSWORD = "qwe123"
CAPSOLVER_KEY = "CAP-8CA9DE27C00014FD6C53B6B3D151C5D956B787187C33A442D0E8969303375BBB"
MERCHANT = "tkgemtlbf7"

# Global proxy counter
proxy_counter = 0

def get_next_proxy():
    """Get next proxy in rotation"""
    global proxy_counter
    if not PROXIES:
        return None
    proxy = PROXIES[proxy_counter % len(PROXIES)]
    proxy_counter += 1
    return proxy

def get_proxy_url(proxy):
    """Convert proxy dict to URL format"""
    if not proxy:
        return None
    return f"http://{proxy['username']}:{proxy['password']}@{proxy['host']}:{proxy['port']}"

def create_proxied_session(proxy):
    """Create requests session with proxy"""
    session = requests.Session()
    if proxy:
        proxy_url = get_proxy_url(proxy)
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
    return session

def create_accounts_from_phone(phone_number):
    """Create 10 accounts based on phone number"""
    accounts = []
    for i in range(1, 11):
        # Format: phone number + 2-digit suffix
        suffix = str(i).zfill(2)
        accounts.append(f"{phone_number}{suffix}")
    return accounts

def solve_captcha_with_capsolver(proxy=None):
    """Solve Botion captcha using Capsolver - with proxy support"""
    
    # Create session with proxy
    session = create_proxied_session(proxy)
    
    # Step 1: Get fresh captcha challenge
    challenge = str(uuid.uuid4())
    load_url = "https://bcaptcha.botion.com/load"
    params = {
        "captcha_id": "2e3984aebc5904671a2a0a7c284b8c79",
        "challenge": challenge,
        "client_type": "web",
        "lang": "fil",
        "callback": f"botion_{int(time.time()*1000)}"
    }
    
    headers = {
        "Accept": "*/*",
        "Referer": "https://www.pinoy365.one/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": f"captcha_v4_user={uuid.uuid4().hex[:32]}"
    }
    
    # Get captcha data
    print("  [Captcha] Loading captcha challenge...")
    load_response = session.get(load_url, params=params, headers=headers)
    
    if load_response.status_code != 200:
        session.close()
        raise Exception(f"Failed to load captcha: {load_response.status_code}")
    
    # Parse JSONP response
    text = load_response.text
    json_str = text[text.find('(')+1:text.rfind(')')]
    load_data = json.loads(json_str)["data"]
    
    # Step 2: Create Capsolver task
    task_data = {
        "clientKey": CAPSOLVER_KEY,
        "task": {
            "type": "GeeTestTaskProxyless",
            "websiteURL": "https://www.pinoy365.one/",
            "captchaId": "2e3984aebc5904671a2a0a7c284b8c79"
        }
    }
    
    # Create task
    print("  [Captcha] Sending to Capsolver...")
    response = requests.post("https://api.capsolver.com/createTask", json=task_data)
    result = response.json()
    
    if "taskId" not in result:
        session.close()
        raise Exception(f"Failed to create Capsolver task: {result}")
    
    task_id = result["taskId"]
    
    # Poll for result
    result_data = {
        "clientKey": CAPSOLVER_KEY,
        "taskId": task_id
    }
    
    for attempt in range(30):
        time.sleep(1)
        result = requests.post("https://api.capsolver.com/getTaskResult", json=result_data)
        result_json = result.json()
        
        if result_json.get("status") == "ready":
            solution = result_json.get("solution")
            print(f"  [Captcha] Solved!")
            
            captcha_solution = {
                "captcha_id": "2e3984aebc5904671a2a0a7c284b8c79",
                "lot_number": solution.get("lot_number", ""),
                "pass_token": solution.get("pass_token", ""),
                "gen_time": solution.get("gen_time", ""),
                "captcha_output": solution.get("captcha_output", "")
            }
            
            if not all([captcha_solution["lot_number"], 
                       captcha_solution["pass_token"], 
                       captcha_solution["gen_time"], 
                       captcha_solution["captcha_output"]]):
                captcha_solution["lot_number"] = captcha_solution["lot_number"] or load_data["lot_number"]
            
            session.close()
            return captcha_solution
            
        elif result_json.get("status") == "processing":
            print(f"  [Captcha] Processing... ({attempt+1}/30)")
            continue
        else:
            session.close()
            raise Exception(f"Captcha solving failed: {result_json}")
    
    session.close()
    raise Exception("Captcha solving timeout")

async def login_and_logout(username, cycle_num, proxy):
    """Single login and logout cycle for an account"""
    
    print(f"  🔄 Cycle {cycle_num}/5")
    
    # Create session with proxy
    session = create_proxied_session(proxy)
    
    try:
        async with async_playwright() as p:
            # Launch browser with proxy
            browser_args = {}
            if proxy:
                browser_args = {
                    "proxy": {
                        "server": f"http://{proxy['host']}:{proxy['port']}",
                        "username": proxy['username'],
                        "password": proxy['password']
                    }
                }
            
            browser = await p.chromium.launch(headless=True, **browser_args)
            page = await browser.new_page()
            await page.goto("about:blank")

            # Load encryption scripts
            await page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.1.1/crypto-js.min.js")
            await page.add_script_tag(url="https://www.pinoy365.one/js/encrypt.js?v=15256")

            # Get RSA key through proxy
            ts = str(int(time.time() * 1000))
            rsa_response = session.get(f"https://www.pinoy365.one/wps/session/key/rsa?_={ts}")
            rsa_hex = rsa_response.text.strip()

            # Generate AES key
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            aes_key = "".join(random.choice(chars) for _ in range(16))
            
            # Solve captcha using same proxy
            try:
                captcha_solution = solve_captcha_with_capsolver(proxy)
            except Exception as e:
                print(f"     ❌ Captcha failed")
                await browser.close()
                session.close()
                return False

            # Create login payload
            payload = {
                "username": username,
                "password": PASSWORD,
                "captcha": None,
                "type": "username",
                "geetestValidateV4": captcha_solution,
                "isSms": False,
                "loginDeviceId": str(uuid.uuid4())
            }

            payload_str = json.dumps(payload, separators=(',', ':'))

            # DES Encrypt (X-Digest)
            des_code = f"""
            (function() {{
                const key8bytes = "{aes_key[:8]}".padEnd(8, "\\\\0");
                const keyBytes = CryptoJS.enc.Utf8.parse(key8bytes);
                const encrypted = CryptoJS.DES.encrypt({json.dumps(payload_str)}, keyBytes, {{
                    mode: CryptoJS.mode.ECB,
                    padding: CryptoJS.pad.Pkcs7
                }});
                return encrypted.toString();
            }})()
            """
            x_digest = await page.evaluate(des_code)

            # RSA encrypt reversed AES
            reversed_key = aes_key[::-1]
            rsa_code = f"""
            (function() {{
                window.setMaxDigits(130);
                var rsa = new window.RSAKeyPair("10001", "", "{rsa_hex}");
                return window.encryptedString(rsa, "{reversed_key}");
            }})()
            """
            rsa_value = await page.evaluate(rsa_code)

            # Headers
            headers = {
                "Language": "EN",
                "Merchant": MERCHANT,
                "Encryption": rsa_value,
                "X-Digest": x_digest,
                "X-Rsa": rsa_hex,
                "X-Timestamp": str(int(time.time() * 1000)),
                "Content-Type": "application/json",
            }

            # LOGIN
            resp = session.post(
                "https://www.pinoy365.one/wps/session/login",
                headers=headers,
                json={"value": x_digest}
            )

            # Check login result
            try:
                resp_json = resp.json()
                if resp.status_code == 200 and resp_json.get("success") == True:
                    token = resp_json['value'].get('token')
                    print(f"     ✅ Login OK")
                    
                    # LOGOUT
                    logout_headers = {
                        "Language": "EN",
                        "Merchant": MERCHANT,
                        "Authorization": token,
                        "Content-Type": "application/json",
                    }
                    
                    logout_resp = session.post(
                        "https://www.pinoy365.one/wps/session/logout",
                        headers=logout_headers,
                        json={}
                    )
                    
                    if logout_resp.status_code == 200:
                        print(f"     ✅ Logout OK")
                    else:
                        print(f"     ⚠️ Logout issue")
                    
                    await browser.close()
                    session.close()
                    return True
                else:
                    print(f"     ❌ Login failed")
                    await browser.close()
                    session.close()
                    return False
            except Exception as e:
                print(f"     ❌ Login failed")
                await browser.close()
                session.close()
                return False
                
    except Exception as e:
        print(f"     ❌ Error: {str(e)}")
        session.close()
        return False

async def process_account(username, queue=None):
    """Process one account with 5 login-logout cycles"""
    
    # Send update
    if queue:
        queue.put({
            'type': 'log',
            'message': f"\n📱 Processing {username}"
        })
    
    successful_cycles = 0
    
    for cycle in range(1, 6):  # 5 cycles
        # Get proxy for this cycle
        proxy = get_next_proxy()
        
        # Perform login and logout
        result = await login_and_logout(username, cycle, proxy)
        
        if result:
            successful_cycles += 1
            if queue:
                queue.put({
                    'type': 'cycle_success',
                    'username': username,
                    'cycle': cycle
                })
        else:
            if queue:
                queue.put({
                    'type': 'cycle_fail',
                    'username': username,
                    'cycle': cycle
                })
        
        # 2 seconds delay between cycles (except after last cycle)
        if cycle < 5:
            await asyncio.sleep(2)
    
    if queue:
        queue.put({
            'type': 'account_complete',
            'username': username,
            'successful_cycles': successful_cycles
        })
    
    return successful_cycles > 0

async def process_phone_number(phone_number, queue=None):
    """Main function to process phone number"""
    
    # Create accounts from phone number
    accounts = create_accounts_from_phone(phone_number)
    
    if queue:
        queue.put({
            'type': 'init',
            'total': len(accounts),
            'message': f"🚀 Processing {len(accounts)} accounts"
        })
    
    successful_accounts = 0
    failed_accounts = 0
    results = []
    
    for i, username in enumerate(accounts, 1):
        if queue:
            queue.put({
                'type': 'account_start',
                'account': i,
                'total': len(accounts),
                'username': username
            })
        
        try:
            success = await process_account(username, queue)
            if success:
                successful_accounts += 1
                results.append({'username': username, 'status': 'success'})
            else:
                failed_accounts += 1
                results.append({'username': username, 'status': 'failed'})
        except Exception as e:
            failed_accounts += 1
            results.append({'username': username, 'status': 'error', 'error': str(e)})
            if queue:
                queue.put({
                    'type': 'error',
                    'message': f"Error on {username}: {str(e)[:50]}"
                })
        
        # 2 seconds delay between accounts
        if i < len(accounts):
            await asyncio.sleep(2)
    
    # Final summary
    summary = {
        'total': len(accounts),
        'successful': successful_accounts,
        'failed': failed_accounts,
        'rate': f"{(successful_accounts/len(accounts)*100):.1f}%",
        'results': results
    }
    
    return summary