import socket
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/packet-tracer", tags=["Packet Tracer IPC"])

@router.get("/status")
def check_pt_status():
    """
    Comprueba si Cisco Packet Tracer está ejecutándose y escuchando en el puerto IPC (39000).
    """
    host = settings.PT_IPC_HOST
    port = settings.PT_IPC_PORT
    is_connected = False
    details = ""

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        result = s.connect_ex((host, port))
        if result == 0:
            is_connected = True
            details = f"Conexión exitosa a Cisco Packet Tracer IPC en {host}:{port}."
        else:
            details = f"Puerto {port} cerrado. Asegúrate de activar 'Extensions > IPC' en Packet Tracer."
        s.close()
    except Exception as e:
        details = f"No se pudo conectar a Packet Tracer ({e})."

    return {
        "pt_ipc_host": host,
        "pt_ipc_port": port,
        "is_active": is_connected,
        "message": details,
        "instructions": (
            "En Cisco Packet Tracer: Menú 'Extensions' -> 'IPC' -> Iniciar servicio para sincronización en tiempo real."
        )
    }
