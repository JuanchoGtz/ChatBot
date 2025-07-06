from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
import openai
import os
import json

load_dotenv()
#Key
openai.api_key = os.getenv("OPENAI_API_KEY") 

# Config
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key='secretkey')
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# DB Setup
DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String)  # 'admin' or 'user'

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)  # computer or accessory
    name = Column(String)
    description = Column(String)
    price = Column(Float)
    cpu = Column(String, nullable=True)
    ram = Column(String, nullable=True)
    storage = Column(String, nullable=True)
    gpu = Column(String, nullable=True)
    os = Column(String, nullable=True)
    ports = Column(String, nullable=True)


Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Routes

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return templates.TemplateResponse("index.html", {"request": request, "products": products})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user and user.role == "admin":
        request.session['user'] = username
        return RedirectResponse(url="/admin/add_product", status_code=302)
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)



@app.post("/admin/add_product")
def add_product(
    request: Request,
    type: str = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    cpu: str = Form(None),
    ram: str = Form(None),
    storage: str = Form(None),
    gpu: str = Form(None),
    os: str = Form(None),
    ports: str = Form(None),
    db: Session = Depends(get_db)
):
    if not request.session.get('user'):
        raise HTTPException(status_code=401, detail="Unauthorized")
    product = Product(
        type=type,
        name=name,
        description=description,
        price=price,
        cpu=cpu,
        ram=ram,
        storage=storage,
        gpu=gpu,
        os=os,
        ports=ports
    )
    db.add(product)
    db.commit()
    return RedirectResponse(url="/", status_code=302)



@app.post("/admin/add_product")
def add_product(request: Request, name: str = Form(...), description: str = Form(...), price: float = Form(...), db: Session = Depends(get_db)):
    if not request.session.get('user'):
        raise HTTPException(status_code=401, detail="Unauthorized")
    product = Product(name=name, description=description, price=price)
    db.add(product)
    db.commit()
    return RedirectResponse(url="/", status_code=302)

#Route Chat
@app.post("/api/chat")
async def chatbot_endpoint(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    user_message = data.get("message")

    # Prompt para GPT: que devuelva JSON estructurado
    prompt = f"""
Eres un asistente de tienda de computadoras. Extrae la intención del usuario y devuélvela en JSON con los campos:
- accion: 'listar' o 'contar'
- filtros: campos como ram, cpu, gpu, type, etc.

Ejemplo de respuesta: {{"accion": "contar", "filtros": {{"ram": "16GB"}}}}.

Pregunta del usuario: "{user_message}"
"""

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un asistente de tienda, devuelves solo JSON válido."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200
    )

    #  Parsea JSON
    gpt_reply = response['choices'][0]['message']['content']
    try:
        parsed = json.loads(gpt_reply)
    except json.JSONDecodeError:
        parsed = {"accion": "error", "filtros": {}}

    accion = parsed.get('accion')
    filtros = parsed.get('filtros', {})

    #  Construye consulta SQL
    query = db.query(Product)
    if 'ram' in filtros:
        query = query.filter(Product.ram.ilike(f"%{filtros['ram']}%"))
    if 'cpu' in filtros:
        query = query.filter(Product.cpu.ilike(f"%{filtros['cpu']}%"))
    if 'gpu' in filtros:
        query = query.filter(Product.gpu.ilike(f"%{filtros['gpu']}%"))
    if 'type' in filtros:
        query = query.filter(Product.type.ilike(f"%{filtros['type']}%"))

    #  Ejecuta acción
    if accion == 'contar':
        result = query.count()
        bot_response = f"Hay {result} productos que cumplen con tu búsqueda."
    elif accion == 'listar':
        results = query.all()
        if results:
            names = ', '.join([p.name for p in results])
            bot_response = f"Los productos encontrados son: {names}."
        else:
            bot_response = "No encontré productos que coincidan."
    else:
        bot_response = "No entendí tu pregunta, ¿puedes reformularla?"

    return JSONResponse(content={"response": bot_response})