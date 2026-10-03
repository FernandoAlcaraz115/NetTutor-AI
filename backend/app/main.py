import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.api.routes_topology import router as topology_router
from app.api.routes_diagnostics import router as diagnostics_router
from app.api.routes_tutor import router as tutor_router
from app.api.routes_packet_tracer import router as pt_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Laboratorio Inteligente y Tutor Socrático para Prácticas de Redes (Cisco Packet Tracer)"
)

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar Endpoints de la API
app.include_router(topology_router, prefix=settings.API_PREFIX)
app.include_router(diagnostics_router, prefix=settings.API_PREFIX)
app.include_router(tutor_router, prefix=settings.API_PREFIX)
app.include_router(pt_router, prefix=settings.API_PREFIX)

# Montar frontend estático si existe
frontend_path = settings.FRONTEND_DIR
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/")
    async def serve_index():
        index_file = frontend_path / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "NetTutorIA API activa. Frontend en construcción."}
