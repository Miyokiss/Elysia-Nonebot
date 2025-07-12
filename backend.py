from flask import Flask
from src.clover_sqlite.models.questions import Question
app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello World!"

@app.route("/list")
async def list_data():
    return await Question.fetch()

@app.route("/init")
async def init_data():
    if await Question.insert_one("你好", "你好哦"):
        return "success"

    return "failed"

def start_flask():
    print("Flask启动中...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)