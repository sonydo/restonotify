# main.py
import os
from typing import List
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from sqlmodel import SQLModel, Field, create_engine, Session, select

# Configuración de base de datos persistente para la nube
# Render borra los archivos locales al reiniciar en su plan gratuito. 
# Nota: Para persistencia real a largo plazo en Render Free se usa una BD externa, 
# pero este código inicial te generará el archivo funcional en '/tmp'.
DATABASE_URL = "sqlite:////tmp/restonotify_cloud.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# ==========================================
# MODELOS DE LA BASE DE DATOS
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
# CONFIGURACIÓN DE LA APP
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
        raise HTTPException(status_code=401, detail="Token inválido")
    return restaurant

# ==========================================
# ENDPOINTS DE LA API
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
    
    # Aquí se dispara la integración real con Meta Cloud API
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
# INTERFAZ WEB DEL FRONTEND (HTML EMBEBIDO)
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def read_index():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RestoNotify - Panel de Cocina</title>
        <script src="https://jsdelivr.net"></script>
        <style>button { touch-action: manipulation; }</style>
    </head>
    <body class="bg-slate-900 text-slate-100 font-sans min-h-screen flex flex-col select-none">
        <header class="bg-slate-800 border-b border-slate-700 px-6 py-4 flex justify-between items-center shadow-md">
            <div class="flex items-center space-x-3">
                <span class="text-2xl">🍽️</span>
                <div>
                    <h1 class="text-xl font-bold tracking-wide text-emerald-400">RESTO-NOTIFY</h1>
                    <p class="text-xs text-slate-400 font-medium">Panel de Control Cloud</p>
                </div>
            </div>
            <div id="clock" class="text-xl font-mono bg-slate-950 px-3 py-1 rounded border border-slate-700 text-slate-300">00:00:00</div>
        </header>

        <main class="flex-1 p-6 space-y-8 overflow-y-auto">
            <section>
                <div class="flex items-center space-x-2 mb-4 border-b border-emerald-500/30 pb-2">
                    <span class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></span>
                    <h2 class="text-lg font-bold uppercase tracking-wider text-emerald-400">En Preparación</h2>
                </div>
                <div id="active-orders" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"></div>
            </section>

            <section>
                <div class="flex items-center space-x-2 mb-4 border-b border-amber-500/30 pb-2">
                    <span class="w-3 h-3 rounded-full bg-amber-500"></span>
                    <h2 class="text-lg font-bold uppercase tracking-wider text-amber-400">Notificados / Esperando Retiro</h2>
                </div>
                <div id="notified-orders" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"></div>
            </section>
        </main>

        <script>
            const urlParams = new URLSearchParams(window.location.search);
            const RESTAURANT_TOKEN = urlParams.get('token');

            if (!RESTAURANT_TOKEN) {
                alert("Error: Falta el parámetro ?token= en la URL");
            }

            async function loadOrders() {
                if (!RESTAURANT_TOKEN) return;
                try {
                    const response = await fetch('/v1/orders/active', {
                        headers: { "X-Restaurant-Token": RESTAURANT_TOKEN }
                    });
                    if (!response.ok) throw new Error("No autorizado");
                    const orders = await response.json();
                    
                    document.getElementById('active-orders').innerHTML = "";
                    document.getElementById('notified-orders').innerHTML = "";

                    orders.forEach(order => {
                        if (order.status === "PREPARACION") renderPrep(order);
                        else if (order.status === "NOTIFICADO") renderNotified(order);
                    });
                } catch (e) { console.error(e); }
            }

            function renderPrep(order) {
                const html = `<div class="bg-slate-800 border-2 border-slate-700 rounded-xl p-5 flex flex-col justify-between min-h-[180px]" id="order-${order.id}">
                    <div><span class="text-2xl font-black text-white font-mono">#${order.id}</span><h3 class="text-lg font-bold text-slate-200 mt-2">${order.customer_name}</h3></div>
                    <button onclick="notifyOrder('${order.id}', '${order.customer_name}')" class="w-full mt-4 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 rounded-lg text-sm uppercase tracking-wider cursor-pointer">🔔 Notificar Listo</button>
                </div>`;
                document.getElementById('active-orders').insertAdjacentHTML('beforeend', html);
            }

            function renderNotified(order) {
                const html = `<div class="bg-slate-800/60 border-2 border-amber-500/50 rounded-xl p-5 flex flex-col justify-between min-h-[180px]" id="order-${order.id}">
                    <div><span class="text-2xl font-black text-slate-300 font-mono">#${order.id}</span><h3 class="text-lg font-bold text-slate-400 mt-2">${order.customer_name}</h3></div>
                    <button onclick="deliverOrder('${order.id}')" class="w-full mt-4 bg-amber-500 hover:bg-amber-400 text-slate-950 font-black py-3 rounded-lg text-sm uppercase tracking-wider cursor-pointer">✔️ Entregado</button>
                </div>`;
                document.getElementById('notified-orders').insertAdjacentHTML('beforeend', html);
            }

            async function notifyOrder(id, name) {
                const card = document.getElementById(`order-${id}`);
                card.style.opacity = '0.5';
                try {
                    const res = await fetch(`/v1/notifications/ready/${id}`, {
                        method: 'POST', headers: { "X-Restaurant-Token": RESTAURANT_TOKEN }
                    });
                    if (res.ok) { card.remove(); renderNotified({id, customer_name: name}); }
                } catch (e) { card.style.opacity = '1'; }
            }

            async function deliverOrder(id) {
                const card = document.getElementById(`order-${id}`);
                card.style.opacity = '0';
                try {
