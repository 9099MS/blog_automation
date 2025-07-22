import os
import time
import re
import requests
import sys
import io
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import google.generativeai as genai
import openai
import anthropic
from PIL import Image
import win32clipboard
from io import BytesIO

# 터미널 인코딩을 UTF-8로 강제 설정 (콘솔이 있는 경우에만)
if sys.stdout and sys.stdout.isatty():
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding = 'utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding = 'utf-8')

# --- 1. AI 설정 및 콘텐츠/이미지 생성 함수 ---
load_dotenv()

def get_api_key(service_name):
    key = os.getenv(service_name)
    if not key: return None
    return key

def clean_html_tags(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def create_blog_post(log_queue, ai_model='gemini', test_mode=False, topic='random', seo_keywords=''):
    if test_mode:
        log_queue.put("🧪 테스트 모드: AI 호출을 건너뛰고 임시 데이터를 반환합니다.")
        time.sleep(1)
        test_title = "테스트 모드: 이미지 업로드 기능 점검"
        test_body = """<p><b>이것은 테스트 모드에서 생성된 가짜 포스트입니다.</b></p>
<p>이미지 업로드와 같은 핵심 기능이 정상적으로 작동하는지 확인합니다.</p>
[REPRESENTATIVE_IMAGE]
<h2>기능 테스트</h2>
<p>이 섹션에서는 이미지 업로드 후 본문이 올바르게 조합되는지 확인합니다.</p>"""
        return test_title, test_body.strip()
    
    try:
        with open("prompt.md", "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        log_queue.put("❌ 'prompt.md' 파일을 찾을 수 없습니다.")
        return None, None

    topic_map = {
        'random': "최근 대중의 관심이 높은 주제(정부정책, 지원금, 여행, 맛집, 생활꿀팁, 자동차, 생활정보 등)를 하나 임의로 선정합니다.",
        'car': "주제는 '자동차'입니다. 자동차와 관련된 최�� 정보를 바탕으로 글을 작성합니다.",
        'government_grant': "주제는 '정부지원금'입니다. 정부의 각종 지원금이나 보조금 정책에 대해 작성합니다.",
        'lifestyle': "주제는 '생활정보'입니다. 일상 생활에 유용한 꿀팁이나 정보를 다룹니다.",
        'travel': "주제는 '여행/축제정보'입니다. 국내외 여행지나 최신 축제 정보를 소개합니다.",
        'issue': "주제는 '최신이슈'입니다. 현재 가장 화제가 되고 있는 사회적, 문화적 이슈를 다룹니다."
    }
    topic_instruction = topic_map.get(topic, f"주제는 '{topic}'입니다. 이 주제에 맞춰 글을 작성합니다.")
    
    current_year = datetime.now().year
    current_month = datetime.now().month
    prompt = prompt_template.format(
        current_year=current_year, 
        current_month=current_month, 
        topic_instruction=topic_instruction,
        seo_keywords=seo_keywords if seo_keywords else "지시된 특정 키워드 없음"
    )

    try:
        log_queue.put(f"🤖 '{ai_model}' 모델에게 블로그 포스트 생성을 요청합니다...")
        content = ""
        api_key_name = ""
        if ai_model == 'gemini': api_key_name = 'GOOGLE_API_KEY'
        elif ai_model == 'chatgpt': api_key_name = 'OPENAI_API_KEY'
        elif ai_model == 'claude': api_key_name = 'ANTHROPIC_API_KEY'
        elif ai_model == 'perplexity': api_key_name = 'PERPLEXITY_API_KEY'

        api_key = get_api_key(api_key_name)
        if not api_key:
            log_queue.put(f"❌ {ai_model} API 키가 .env 파일에 설정되지 않았습니다.")
            return None, None

        if ai_model == 'gemini':
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt, request_options={"timeout": 120})
            content = response.text
        elif ai_model == 'chatgpt':
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
            content = response.choices[0].message.content
        elif ai_model == 'claude':
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(model="claude-3-sonnet-20240229", max_tokens=4096, messages=[{"role": "user", "content": prompt}])
            content = response.content[0].text
        elif ai_model == 'perplexity':
            client = openai.OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
            response = client.chat.completions.create(model="sonar-pro", messages=[{"role": "user", "content": prompt}])
            content = response.choices[0].message.content
        
        log_queue.put("✅ AI로부터 응답을 성공적으로 받았습니다.")
        content = content.strip()
        if not content:
            log_queue.put("❌ AI가 빈 응답을 반환했습니다.")
            return None, None

        if "```html" in content:
            content = content.split("```html")[1].split("```")[0].strip()

        title, body = "", ""
        h1_match = re.search(r'<h1.*?>(.*?)</h1>', content, re.IGNORECASE | re.DOTALL)
        if h1_match:
            title_html = h1_match.group(0)
            title = clean_html_tags(title_html).strip()
            body = content.replace(title_html, '', 1).strip()
        else:
            lines = content.split('\n')
            if lines:
                title = clean_html_tags(lines[0]).strip()
                body = '\n'.join(lines[1:]).strip()

        if not title or not body:
            log_queue.put(f"❌ AI 응답에서 제목/본문 추출 실패. 원본(일부): {content[:200]}...")
            return None, None
        return title, body

    except Exception as e:
        log_queue.put(f"❌ AI 응답 중 오류 발생: {e}")
        return None, None

def generate_image_and_get_path(log_queue, title):
    log_queue.put("🎨 DALL-E 3에게 대표 이미지 생성을 요청합니다...")
    try:
        api_key = get_api_key('OPENAI_API_KEY')
        if not api_key:
            log_queue.put("❌ 이미지 생성을 위한 OpenAI API 키가 없습니다.")
            return None

        client = openai.OpenAI(api_key=api_key)
        image_prompt = f"A high-quality, photorealistic image for a blog post titled '{title}'. Centered main subject, aesthetically pleasing, with a clean background. No text, no letters, no watermarks."
        response = client.images.generate(model="dall-e-3", prompt=image_prompt, size="1024x1024", quality="standard", n=1)
        image_url = response.data[0].url
        log_queue.put("✅ DALL-E 3가 이미지를 성공적으로 생성했습니다.")
        
        log_queue.put("이미지를 임시 파일로 다운로드합니다...")
        image_response = requests.get(image_url)
        image_response.raise_for_status()

        temp_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp")
        image_path = os.path.join(temp_dir, "blog_image.png")
        with open(image_path, "wb") as f:
            f.write(image_response.content)
        
        log_queue.put(f"✅ 이미지를 '{image_path}'에 저장했습니다.")
        return image_path

    except Exception as e:
        log_queue.put(f"❌ 이미지 생성/다운로드 중 오류: {e}")
        return None

def copy_image_to_clipboard(log_queue, image_path):
    """이미지 파일을 클립보드에 복사합니다."""
    try:
        image = Image.open(image_path)
        output = BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        log_queue.put(f"❌ 클립보드 복사 중 오류 발생: {e}")
        return False

# --- 2. Selenium을 이용한 티스토리 포스팅 함수 ---
def post_to_tistory(log_queue, driver, title, body, image_path):
    """로그인된 세션을 이어받아 포스팅을 진행합니다."""
    try:
        wait = WebDriverWait(driver, 20)
        log_queue.put("글쓰기 페이지로 이동합니다...")
        driver.get("https://sporg.tistory.com/manage/newpost/")

        try:
            log_queue.put("임시 저장글 팝업 3초간 확인...")
            alert = WebDriverWait(driver, 3).until(EC.alert_is_present())
            alert.dismiss()
        except TimeoutException:
            log_queue.put("임시 저장글 팝업이 없습니다.")

        log_queue.put("제목을 입력합니다...")
        title_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//textarea[@placeholder='제목을 입력하세요']")))
        title_input.send_keys(title)
        time.sleep(1)

        tistory_img_code = ""
        if image_path:
            log_queue.put("클립보드를 이용해 이미지를 업로드합니다...")
            if not copy_image_to_clipboard(log_queue, image_path):
                log_queue.put("❌ 이미지 복사를 실패했습니다.")
            else:
                try:
                    log_queue.put("에디터(iframe)로 전환합니다...")
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
                    driver.switch_to.frame(0)
               
                    editor_body = wait.until(EC.element_to_be_clickable((By.ID, "tinymce")))
            
                    log_queue.put("에디터를 클릭하고 Ctrl+V (붙여넣기)를 실행합니다...")
                    ActionChains(driver).move_to_element(editor_body).click().key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    
                    log_queue.put("이미지 처리를 위해 5초간 대기합니다...")
                    time.sleep(5)
                    
                    driver.switch_to.default_content()
                    log_queue.put("✅ 이미지 붙여넣기 완료. 원래 페이지로 복귀합니다.")
                    
                except Exception as e:
                    driver.switch_to.default_content()
                    log_queue.put(f"❌ 이미지 붙여넣기 중 오류 발생: {e}")

        log_queue.put("'기본모드' 버튼을 클릭합니다...")
        gmode_button_xpath = "//button[.//span[contains(text(), '기본모드')]]"
        gmode_button = wait.until(EC.element_to_be_clickable((By.XPATH, gmode_button_xpath)))
        gmode_button.click()
        
        log_queue.put("나타난 'HTML' 모드를 강제 클릭합니다...")
        html_mode_option_xpath = "//*[text()='HTML']"
        html_mode_option = wait.until(EC.presence_of_element_located((By.XPATH, html_mode_option_xpath)))
        driver.execute_script("arguments[0].click();", html_mode_option)

        try:
            log_queue.put("작성모드 팝업이 있는지 3초간 확인...")
            alert = WebDriverWait(driver, 3).until(EC.alert_is_present())
            log_queue.put(f"팝업 발견! '{alert.text}' 팝업의 '확인' 버튼을 누릅니다.")
            alert.accept()
        except TimeoutException:
            log_queue.put("작성모드 변경 확인 팝업이 없습니다.")

        log_queue.put("본문 입력창(CodeMirror)을 기다립니다...")
        codemirror_element = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "CodeMirror")))
        
        if image_path:
            log_queue.put("이미지 코드를 추출합니다...")
            editor_content = driver.execute_script("return arguments[0].CodeMirror.getValue();", codemirror_element)
            img_match = re.search(r'(<p>\[##_Image\|.*?_##\]</p>)', editor_content, re.DOTALL)
            if img_match:
                tistory_img_code = img_match.group(1)
                log_queue.put("✅ 티스토리 이미지 코드 추출 완료.")
            else:
                log_queue.put("⚠️ 업로드된 이미지 코드 추출 실패.")
        
        final_body = body.replace("[REPRESENTATIVE_IMAGE]", tistory_img_code)

        log_queue.put("최종 본문을 입력합니다...")
        driver.execute_script("arguments[0].CodeMirror.setValue(arguments[1]);", codemirror_element, final_body)
        
        log_queue.put("변경사항 인식을 위해 키보드 입력 시뮬레이..")
        hidden_textarea = codemirror_element.find_element(By.TAG_NAME, "textarea")
        driver.execute_script("arguments[0].focus();", hidden_textarea)
        time.sleep(0.5)
        
        ActionChains(driver).send_keys_to_element(hidden_textarea, " \n").perform() 
        time.sleep(1)

        log_queue.put("내용 저장을 위해 '기본모드'로 재전환합니다...")
        html_button_xpath = "//button[i[contains(text(), 'HTML')]]"
        html_button = wait.until(EC.element_to_be_clickable((By.XPATH, html_button_xpath)))
        html_button.click()
        time.sleep(2)
      
        log_queue.put("'기본모드' 모드를 강제 클릭!")
        html_mode_option_xpath = "//*[text()='기본모드']"
        html_mode_option = wait.until(EC.presence_of_element_located((By.XPATH, html_mode_option_xpath)))
        driver.execute_script("arguments[0].click();", html_mode_option)

        try:
            log_queue.put("작성모드 변경 팝업 3초간 확인..")
            alert = WebDriverWait(driver, 3).until(EC.alert_is_present())
            log_queue.put(f"팝업 발견! '{alert.text}' 팝업의 '확인' 버튼을 누릅니다.")
            alert.accept()
        except TimeoutException:
            log_queue.put("작성모드 변경 확인 팝업이 없습니다.")

        log_queue.put("기본모드 전환 완료 3초 대기...")
        time.sleep(3)

        log_queue.put("발행 버튼을 클릭합니다...")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='완료']"))).click()
        wait.until(EC.element_to_be_clickable((By.ID, "publish-btn"))).click()

        log_queue.put("포스팅 완료를 기다립니다...")
        time.sleep(5)
        
        final_post_url = driver.current_url
        log_queue.put(f"🎉 포스팅 성공! 발행된 글 주소: {final_post_url}")
        return True
    except Exception as e:
        log_queue.put(f"❌ 포스팅 중 오류 발생: {e}")
        try:
            driver.save_screenshot("error_screenshot.png")
            log_queue.put("'error_screenshot.png' 파일로 현재 화면을 저장했습니다.")
        except: pass
        return False

# --- 3. 메인 실행 부분 ---
def start_blog_automation(log_queue, ai_model='gemini', test_mode=False, topic='random', include_image=True, seo_keywords=''):
    """블로그 자동화 전체 프로세스를 실행하고 성공 여부를 반환합니다."""
    driver = None
    try:
        options = webdriver.ChromeOptions()
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)

        log_queue.put("개인 블로그 관리 페이지로 이동합니다...")
        driver.get("https://sporg.tistory.com/manage")

        time.sleep(2)
        if "login" in driver.current_url:
            log_queue.put("카카오계정으로 로그인을 시도합니다.")
            wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "btn_login"))).click()
            
            TISTORY_ID, TISTORY_PW = get_api_key("TISTORY_ID"), get_api_key("TISTORY_PW")
            if not TISTORY_ID or not TISTORY_PW:
                log_queue.put("❌ 티스토리 ID/PW가 .env에 없습니다.")
                return

            wait.until(EC.presence_of_element_located((By.ID, "loginId--1"))).send_keys(TISTORY_ID)
            wait.until(EC.presence_of_element_located((By.ID, "password--2"))).send_keys(TISTORY_PW)
            wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "btn_g"))).click()
            
            try:
                wait.until_not(EC.url_contains("login"))
                log_queue.put("✅ 로그인 성공!")
            except TimeoutException:
                log_queue.put("‼️ 2차 인증 필요. 3분간 대기합니다...")
                WebDriverWait(driver, 180).until_not(EC.url_contains("login"))
                log_queue.put("✅ 로그인 완료 확인.")
        else:
            log_queue.put("✅ 자동 로그인되었습니다.")

        generated_title, generated_body = create_blog_post(log_queue, ai_model, test_mode, topic, seo_keywords)
        if not generated_title or not generated_body:
            return

        log_queue.put(f"📄 생성된 제목: {generated_title}")
        
        image_path = None
        if "[REPRESENTATIVE_IMAGE]" in generated_body and include_image:
            if test_mode:
                temp_image = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "blog_image.png")
                if os.path.exists(temp_image):
                    log_queue.put(f"🧪 테스트 모드: 기존 이미지 '{temp_image}' 재사용.")
                    image_path = temp_image
                else:
                    log_queue.put("🧪 테스트 모드: 재사용할 이미지 없음.")
            else:
                image_path = generate_image_and_get_path(log_queue, generated_title)

        if image_path:
            log_queue.put("이미지를 클립보드에 복사합니다...")
            if not copy_image_to_clipboard(log_queue, image_path):
                log_queue.put("❌ 이미지 복사 실패, 이미지 없이 포스팅 진행.")
                image_path = None

        post_to_tistory(log_queue, driver, generated_title, generated_body, image_path)

    except Exception as e:
        log_queue.put(f"❌ 자동화 실행 중 치명적 오류: {e}")
    finally:
        if driver:
            log_queue.put("작업 완료. 5초 후 브라우저를 종료합니다.")
            time.sleep(5)
            driver.quit()
        log_queue.put("--- 모든 작업이 종료되었습니다 ---")

if __name__ == "__main__":
    import queue
    
    log_queue = queue.Queue()
    
    def console_logger():
        while True:
            try:
                message = log_queue.get(timeout=1)
                print(message)
                if "모든 작업이 종료되었습니다" in message:
                    break
            except queue.Empty:
                if not logger_thread.is_alive():
                    break
    
    import threading
    logger_thread = threading.Thread(target=console_logger)
    
    automation_thread = threading.Thread(target=start_blog_automation, args=(log_queue, 'gemini', True, 'random', True, ''))
    
    logger_thread.start()
    automation_thread.start()
    automation_thread.join()
    logger_thread.join()