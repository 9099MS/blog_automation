from flask import Flask, render_template, jsonify, request, Response, redirect, url_for, flash
import threading
import queue
import main
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
import logging
from datetime import datetime

logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.WARNING)

app = Flask(__name__)
app.secret_key = 'a-very-secret-key-for-web-app'

log_queue = queue.Queue()
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

def run_automation_in_thread(params):
    with app.app_context():
        main.start_blog_automation(
            log_queue,
            ai_model=params['ai_model'],
            test_mode=params['test_mode'],
            topic=params['topic'],
            include_image=params['include_image'],
            seo_keywords=params['seo_keywords']
        )

@app.route('/')
def index():
    job = scheduler.get_job('scheduled_tistory_post')
    status = ""
    if job:
        status = f"다음 실행 예정: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}"
    return render_template('index.html', schedule_status=status)

@app.route('/run', methods=['POST'])
def run_automation_route():
    run_type = request.form.get('run_type', 'now')
    ai_model = request.form.get('ai_model', 'gemini')
    is_test_mode = request.form.get('test_mode') == 'true'
    include_image = request.form.get('include_image') == 'true'
    topic = request.form.get('topic', 'random')
    if topic == 'custom':
        topic = request.form.get('custom_topic', 'random')
    seo_keywords = request.form.get('seo_keywords', '')

    job_params = {
        'ai_model': ai_model,
        'test_mode': is_test_mode,
        'topic': topic,
        'include_image': include_image,
        'seo_keywords': seo_keywords
    }

    while not log_queue.empty():
        try: log_queue.get_nowait()
        except queue.Empty: continue

    if run_type == 'schedule':
        interval = int(request.form.get('interval', 60))
        
        try:
            scheduler.remove_job('scheduled_tistory_post')
        except JobLookupError:
            pass
            
        scheduler.add_job(
            run_automation_in_thread, 
            'interval', 
            minutes=interval, 
            id='scheduled_tistory_post', 
            args=[job_params],
            replace_existing=True,
            next_run_time=datetime.now()
        )
        return jsonify({'status': 'scheduled', 'message': f"✅ 지금 실행을 시작합니다. 이후 {interval}분 간격으로 스케줄이 등록되었습니다."})
    
    else:
        thread = threading.Thread(target=run_automation_in_thread, args=[job_params])
        thread.start()
        return jsonify({'status': 'running', 'message': "🚀 즉시 실행을 시작합니다..."})

@app.route('/stop_schedule', methods=['POST'])
def stop_schedule():
    try:
        scheduler.remove_job('scheduled_tistory_post')
        flash("✅ 스케줄이 성공적으로 중지되었습니다.", "success")
    except JobLookupError:
        flash("ℹ️ 중지할 스케줄이 없습니다.", "info")
    return redirect(url_for('index'))

@app.route('/stream')
def stream():
    def event_stream():
        while True:
            try:
                message = log_queue.get(timeout=1)
                yield f"data: {message}\n\n"
                if "--- 모든 작업이 종료되었습니다 ---" in message:
                    break
            except queue.Empty:
                yield ": keep-alive\n\n"

    return Response(event_stream(), mimetype='text/event-stream')

if __name__ == '__main__':
    import webbrowser
    # 서버가 완전히 시작될 시간을 벌기 위해 잠시 대기 후 브라우저 열기
    threading.Timer(1.25, lambda: webbrowser.open("http://127.0.0.1:5001")).start()
    print("웹 서버를 시작합니다. http://127.0.0.1:5001 로 접속하세요.")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
