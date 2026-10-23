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

# 数据库连接配置（请确保密码和你的 PostgreSQL 密码一致）
DB_CONFIG = {
    "dbname": "finance_db",
    "user": "postgres",
    "password": "Zx@62653014", # 记得改成你的真实密码
    "host": "localhost",
    "port": "5432"
}

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

# 后端直接托管网页，访问根路径即可
@app.get("/", response_class=HTMLResponse)
def serve_home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>index.html 文件未找到！</h3>"

# 🌟 新增：防止访问 /api 时报 404
@app.get("/api")
def api_root():
    return {"message": "Finance API is running successfully!"}

# 注册接口
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

# 登录接口
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

# 修改密码接口
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

# 获取账本数据
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

# 保存账本数据
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
    uvicorn.run(app, host="0.0.0.0", port=8000)