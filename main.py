import os
from typing import List
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from sqlmodel import SQLModel, Field, create_engine, Session, select

DATABASE_URL = "sqlite:////tmp/restonotify_cloud.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# ==========================================
# DATABASE MODELS
# ==========================================
class Restaurant(SQLModel, table=True):
    id: str = Field(primary_key=True)  
    name: str                          
    api_token: str = Field(index=True) 
    whatsapp_config: str = Field(default="{}") 

class Order(SQLModel, table=True):
    id: str = Field(primary_key=True)  
    restaurant_id: str = Field(foreign_key="restaurant.id", primary_key=True) 
    customer_name: str
    phone_number: str
    status: str = Field(default="PREPARACION") 

# ==========================================
# APP CONFIGURATION
# ==========================================
app = FastAPI(title="RestoNotify Cloud API")

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

async def verify_restaurant(x_restaurant_token: str = Header(...), session: Session = Depends(get_session)):
    statement = select(Restaurant).where(Restaurant.api_token == x_restaurant_token)
    restaurant = session.exec(statement).first()
    if not restaurant:
        raise HTTPException(status_code=401, detail="Token invalido")
    return restaurant

# ==========================================
# API ENDPOINTS
# ==========================================
@app.post("/admin/restaurants")
async def register_restaurant(restaurant: Restaurant, session: Session = Depends(get_session)):
    session.add(restaurant)
    session.commit()
    return {"status": "success", "message": f"Restaurante {restaurant.name} registrado."}

@app.post("/v1/orders")
async def create_order(order: Order, current_restaurant: Restaurant = Depends(verify_restaurant), session: Session = Depends(get_session)):
    order.restaurant_id = current_restaurant.id
    session.add(order)
    session.commit()
    return {"status": "success", "order_id": order.id}

@app.post("/v1/notifications/ready/{order_id}")
async def send_ready_notification(order_id: str, current_restaurant: Restaurant = Depends(verify_restaurant), session: Session = Depends(get_session)):
    statement = select(Order).where(Order.id == order_id, Order.restaurant_id == current_restaurant.id)
    order = session.exec(statement).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    order.status = "NOTIFICADO"
    session.add(order)
    session.commit()
    return {"status": "success"}

@app.post("/v1/orders/{order_id}/deliver")
async def deliver_order(order_id: str, current_restaurant: Restaurant = Depends(verify_restaurant), session: Session = Depends(get_session)):
    statement = select(Order).where(Order.id == order_id, Order.restaurant_id == current_restaurant.id)
    order = session.exec(statement).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    order.status = "ENTREGADO"
    session.add(order)
    session.commit()
    return {"status": "success"}

@app.get("/v1/orders/active", response_model=List[Order])
async def get_active_orders(current_restaurant: Restaurant = Depends(verify_restaurant), session: Session = Depends(get_session)):
    statement = select(Order).where(Order.restaurant_id == current_restaurant.id, Order.status != "ENTREGADO")
    return session.exec(statement).all()

# ==========================================
# FRONTEND ENTRYPOINT
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def read_index():
    # Busca de forma automatica en la raiz o en subcarpetas tipicas
    posibles_rutas = ["index.html", "frontend/index.html", "backend/index.html"]
    
    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                return f.read()
                
    return "Error: index.html no encontrado en el servidor. Verifique las carpetas en GitHub."
