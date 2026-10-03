import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
ROOT_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
env_path = ROOT_DIR / ".env"
load_dotenv(dotenv_path=env_path)

class Settings:
    PROJECT_NAME: str = "NetTutorIA"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"
    
    # Clave de Gemini (opcional pero recomendada para el tutor socrático completo)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    # Packet Tracer IPC Settings (por defecto puerto 39000)
    PT_IPC_HOST: str = os.getenv("PT_IPC_HOST", "127.0.0.1")
    PT_IPC_PORT: int = int(os.getenv("PT_IPC_PORT", "39000"))
    
    # Carpetas estáticas
    ROOT_DIR: Path = ROOT_DIR
    FRONTEND_DIR: Path = ROOT_DIR / "frontend"

settings = Settings()
