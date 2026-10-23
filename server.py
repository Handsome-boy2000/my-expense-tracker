from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
import json
import os
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
        print("=== 注册接口报错 ===")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/login")
def login_user(data: AuthData):
    try:
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
    except HTTPException as he:
        raise he
    except Exception as e:
        print("=== 登录接口报错 ===")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/change-password")
def change_password(data: ChangePasswordData):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE email = %s", (data.username,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="用户不存在")
        if row[0] != data.old_password:
            raise HTTPException(status_code=400, detail="原密码不正确")
        
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (data.new_password, data.username))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print("=== 修改密码报错 ===")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/ledgers/{user_id}")
def get_ledgers(user_id: str):
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
    except Exception as e:
        print("=== 获取账单报错 ===")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/ledgers")
def save_ledgers(data: LedgerData):
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
    except Exception as e:
        print("=== 保存账单报错 ===")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)