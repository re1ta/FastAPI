from datetime import datetime

from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, Sequence, DateTime, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from typing import List, Optional
from pydantic import BaseModel

app = FastAPI()

DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base(metadata=MetaData())


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, Sequence("item_id_seq"), primary_key=True, index=True)
    name = Column(String(50))
    description = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class History(Base):
    __tablename__ = "history"
    id = Column(Integer, Sequence("item_id_seq"), primary_key=True, index=True)
    operation = Column(String(50))
    time = Column(DateTime(timezone=True), server_default=func.now())


class HistoryCreate(BaseModel):
    operation: str


class ItemCreate(BaseModel):
    name: str
    description: Optional[str]


class ItemRead(BaseModel):
    id: int
    name: str
    description: Optional[str]


Base.metadata.create_all(bind=engine)


def create_item(db: Session, item: ItemCreate):
    db_item = Item(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    history_item = HistoryCreate(operation="вещь создана")
    write_history(db, history_item)

    return db_item


def write_history(db: Session, history: HistoryCreate):
    db_history = History(operation=history.operation, time=datetime.utcnow())
    db.add(db_history)
    db.commit()
    db.refresh(db_history)
    return db_history


def get_items(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Item).offset(skip).limit(limit).all()


def get_item(db: Session, item_id: int):
    return db.query(Item).filter(Item.id == item_id).first()


def update_item(db: Session, item_id: int, updated_item: ItemCreate):
    db_item = db.query(Item).filter(Item.id == item_id).first()
    db_item.name = updated_item.name
    db_item.description = updated_item.description
    db.commit()
    db.refresh(db_item)

    history_item = HistoryCreate(operation="вещь обновлена")
    write_history(db, history_item)

    return db_item


def delete_item(db: Session, item_id: int):
    db_item = db.query(Item).filter(Item.id == item_id).first()
    db.delete(db_item)
    db.commit()

    history_item = HistoryCreate(operation="вещь удалена")
    write_history(db, history_item)

    return db_item


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/items/", response_model=ItemRead)
def create_item_api(item: ItemCreate, db: Session = Depends(get_db)):
    return create_item(db, item)


@app.get("/items/{item_id}", response_model=ItemRead)
def read_item(item_id: int, db: Session = Depends(get_db)):
    db_item = get_item(db, item_id=item_id)
    if db_item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemRead(id=db_item.id, name=db_item.name, description=db_item.description)


@app.put("/items/{item_id}", response_model=ItemRead)
def update_item_api(item_id: int, item: ItemCreate, db: Session = Depends(get_db)):
    updated_item = update_item(db, item_id, item)
    return ItemRead(id=updated_item.id, name=updated_item.name, description=updated_item.description)


@app.delete("/items/{item_id}", response_model=ItemRead)
def delete_item_api(item_id: int, db: Session = Depends(get_db)):
    deleted_item = delete_item(db, item_id)
    if deleted_item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemRead(id=deleted_item.id, name=deleted_item.name, description=deleted_item.description)


@app.get("/items/", response_model=List[ItemRead])
def read_items(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    items = get_items(db, skip=skip, limit=limit)
    return [ItemRead(id=item.id, name=item.name, description=item.description) for item in items]


class WebSocketManager:
    def __init__(self):
        self.active_connections = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_notification(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = WebSocketManager()


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_notification(f"Client {client_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=10000)
