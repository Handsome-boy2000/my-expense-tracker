from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
import json
import os
import uuid
import traceback

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "dbname": os.environ.get("DB_NAME", "postgres"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", ""),
    "port": os.environ.get("DB_PORT", "5432")
}

def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print("=== 数据库连接失败 ===")
        traceback.print_exc()
        raise e

# 初始化数据库表结构（确保 users 表有 active_token 字段）
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email VARCHAR(255) PRIMARY KEY,
                password_hash VARCHAR(255) NOT NULL,
                active_token VARCHAR(255)
            );
            CREATE TABLE IF NOT EXISTS user_ledgers (
                user_id VARCHAR(255) PRIMARY KEY,
                content JSONB,
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("初始化数据库表失败:", e)

init_db()

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

def verify_token(user_id: str, token: str):
    if not token:
        raise HTTPException(status_code=401, detail="未授权，请重新登录")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT active_token FROM users WHERE email = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row or row[0] != token:
        raise HTTPException(status_code=401, detail="您的账号已在其他设备登录，当前会话已失效")

@app.get("/", response_class=HTMLResponse)
def serve_home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>index.html 文件未找到！</h3>"

@app.post("/api/register")
def register_user(data: AuthData):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s)", (data.username, data.password))
        conn.commit()
        cur.execute("INSERT INTO user_ledgers (user_id, content) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
                    (data.username, json.dumps({"默认账本": []})))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="注册失败或用户名已存在")

@app.post("/api/login")
def login_user(data: AuthData):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE email = %s", (data.username,))
        row = cur.fetchone()
        
        if not row:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="用户不存在，请先注册")
        if row[0] != data.password:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="密码错误")
        
        # 生成唯一的会话 Token，实现单设备排他登录
        session_token = str(uuid.uuid4())
        cur.execute("UPDATE users SET active_token = %s WHERE email = %s", (session_token, data.username))
        conn.commit()
        cur.close()
        conn.close()
        
        return {"status": "success", "username": data.username, "token": session_token}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/change-password")
def change_password(data: ChangePasswordData, x_token: str = Header(None)):
    verify_token(data.username, x_token)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE email = %s", (data.username,))
        row = cur.fetchone()
        if not row or row[0] != data.old_password:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="原密码不正确")
        
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (data.new_password, data.username))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/ledgers/{user_id}")
def get_ledgers(user_id: str, x_token: str = Header(None)):
    verify_token(user_id, x_token)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT content FROM user_ledgers WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"content": row[0]}
        return {"content": {"默认账本": []}}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/ledgers")
def save_ledgers(data: LedgerData, x_token: str = Header(None)):
    verify_token(data.user_id, x_token)
    try:
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
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)