from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自动从环境变量读取（如果在云端部署，直接读取环境变量；如果在本地测试，可以写死测试）
DB_CONFIG = {
    "dbname": os.environ.get("DB_NAME"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "host": os.environ.get("DB_HOST"),
    "port": os.environ.get("DB_PORT", "5432")
}

# 增加安全检查：如果没配环境变量，直接在启动时报错
if not all(DB_CONFIG.values()):
    raise ValueError("数据库环境变量未完整配置！请检查 Render后台的 Environment 设置。")

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

class AuthData(BaseModel):
    username: str
    password: str

class ChangePasswordData(BaseModel):
    username: str
    old_password: str
    new_password: str

class LedgerData(BaseModel):
    user_id: str
    content: dict

@app.get("/", response_class=HTMLResponse)
def serve_home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>index.html 文件未找到！</h3>"

@app.get("/api")
def api_root():
    return {"message": "Finance API is running successfully on cloud!"}

@app.post("/api/register")
def register_user(data: AuthData):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s)", (data.username, data.password))
        conn.commit()
        cur.execute("INSERT INTO user_ledgers (user_id, content) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
                    (data.username, json.dumps({"默认账本": []})))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="用户名已存在或注册失败")
    finally:
        cur.close()
        conn.close()
    return {"status": "success"}

@app.post("/api/login")
def login_user(data: AuthData):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE email = %s", (data.username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=400, detail="用户不存在，请先注册")
    if row[0] != data.password:
        raise HTTPException(status_code=400, detail="密码错误")
    
    return {"status": "success", "username": data.username}

@app.post("/api/change-password")
def change_password(data: ChangePasswordData):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM users WHERE email = %s", (data.username,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="用户不存在")
        if row[0] != data.old_password:
            raise HTTPException(status_code=400, detail="原密码不正确")
        
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (data.new_password, data.username))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return {"status": "success"}

@app.get("/api/ledgers/{user_id}")
def get_ledgers(user_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT content FROM user_ledgers WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {"content": row[0]}
    return {"content": {"默认账本": []}}

@app.post("/api/ledgers")
def save_ledgers(data: LedgerData):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_ledgers (user_id, content, updated_at) 
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id) 
        DO UPDATE SET content = EXCLUDED.content, updated_at = NOW();
    """, (data.user_id, json.dumps(data.content)))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)